import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "feedback_bundle.py"
EXAMPLE = ROOT / "assets" / "feedback-example.json"
spec = importlib.util.spec_from_file_location("feedback_bundle", SCRIPT)
feedback = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feedback)


class FeedbackBundleTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def test_example_and_single_unknown_are_valid(self):
        result = feedback.validate_data(self.data)
        self.assertTrue(result["ready"])
        self.assertEqual(self.data["candidates"][0]["status"], "unverified")
        self.assertEqual(self.data["candidates"][0]["evaluation"]["conclusion"], "inconclusive")

    def test_single_case_cannot_be_verified(self):
        self.data["candidates"][0]["status"] = "verified"
        with self.assertRaises(feedback.ValidationError) as caught:
            feedback.validate_data(self.data)
        self.assertIn("single-case", str(caught.exception))

    def test_training_heldout_leakage_is_rejected(self):
        evaluation = self.data["candidates"][0]["evaluation"]
        evaluation["heldout_case_ids"] = [evaluation["training_case_ids"][0]]
        with self.assertRaises(feedback.ValidationError) as caught:
            feedback.validate_data(self.data)
        self.assertIn("must not overlap", str(caught.exception))

    def test_evidence_and_counterexamples_are_training_only(self):
        evaluation = self.data["candidates"][0]["evaluation"]
        evaluation["training_case_ids"] = ["case-synthetic-001"]
        with self.assertRaises(feedback.ValidationError) as caught:
            feedback.validate_data(self.data)
        self.assertIn("every evidence and counterexample case", str(caught.exception))

    def test_cross_candidate_leakage_and_source_count_are_rejected(self):
        second = copy.deepcopy(self.data["candidates"][0])
        second["id"] = "second-candidate"
        second["evidence"][0]["case_id"] = "case-synthetic-004"
        second["counterexamples"] = []
        second["evaluation"]["training_case_ids"] = ["case-synthetic-004"]
        second["evaluation"]["heldout_case_ids"] = ["case-synthetic-001"]
        self.data["candidates"].append(second)
        with self.assertRaises(feedback.ValidationError) as caught:
            feedback.validate_data(self.data)
        self.assertIn("training in one candidate and held out", str(caught.exception))
        self.assertIn("unique source case ids", str(caught.exception))

    def test_unknown_or_absent_evaluation_cannot_claim_improvement(self):
        evaluation = self.data["candidates"][0]["evaluation"]
        evaluation["conclusion"] = "improved"
        with self.assertRaises(feedback.ValidationError):
            feedback.validate_data(self.data)
        evaluation["baseline_result"] = "fail"
        evaluation["candidate_result"] = "pass"
        evaluation["heldout_case_ids"] = []
        with self.assertRaises(feedback.ValidationError):
            feedback.validate_data(self.data)

    def test_validate_reports_not_ready_but_build_refuses(self):
        self.data["share_authorized"] = False
        self.assertEqual(feedback.validate_data(self.data)["status"], "not_ready")
        with self.assertRaises(feedback.ValidationError):
            feedback.build_bundle(self.data, self.root / "bundle")

    def test_privacy_findings_do_not_echo_values(self):
        secret_value = "person@example.com"
        self.data["candidates"][0]["rationale"] = secret_value
        findings = feedback.scan_privacy(self.data)
        self.assertEqual(findings[0]["type"], "email")
        self.assertNotIn(secret_value, json.dumps(findings))
        path = self.root / "bad.json"
        path.write_text(json.dumps(self.data), encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPT), "validate", str(path)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(secret_value, result.stderr)
        self.assertIn("possible email", result.stderr)

    def test_schema_extra_raw_field_path_escape_and_injection_rejected(self):
        variants = []
        extra = copy.deepcopy(self.data); extra["raw_conversations"] = ["raw"] ; variants.append(extra)
        traversal = copy.deepcopy(self.data); traversal["candidates"][0]["target"]["value"] = "references/../secret.md"; variants.append(traversal)
        absolute = copy.deepcopy(self.data); absolute["candidates"][0]["target"]["value"] = "/tmp/secret.md"; variants.append(absolute)
        unapproved = copy.deepcopy(self.data); unapproved["candidates"][0]["target"]["value"] = "references/unapproved.md"; variants.append(unapproved)
        injection = copy.deepcopy(self.data); injection["candidates"][0]["proposed_change"] = "查看[外部材料](https://invalid.example)"; variants.append(injection)
        image = copy.deepcopy(self.data); image["candidates"][0]["rationale"] = "![图](data:image/png;base64,abc)"; variants.append(image)
        for item in variants:
            with self.subTest(item=item), self.assertRaises(feedback.ValidationError):
                feedback.validate_data(item)

    def test_real_knowledge_targets_are_supported(self):
        target = self.data["candidates"][0]["target"]
        for target_type, value in (
            ("knowledge_id", "M-AS01"),
            ("knowledge_id", "M-PS"),
            ("reference_path", "knowledge/methods/refund_check.md"),
        ):
            with self.subTest(value=value):
                target["type"] = target_type
                target["value"] = value
                self.assertTrue(feedback.validate_data(self.data)["valid"])

    def test_invalid_types_return_validation_errors(self):
        variants = []
        bad_status = copy.deepcopy(self.data); bad_status["candidates"][0]["status"] = {}; variants.append(bad_status)
        bad_result = copy.deepcopy(self.data); bad_result["candidates"][0]["evaluation"]["baseline_result"] = {}; variants.append(bad_result)
        bad_case = copy.deepcopy(self.data); bad_case["candidates"][0]["evaluation"]["training_case_ids"] = [{}]; variants.append(bad_case)
        bad_outcome = copy.deepcopy(self.data); bad_outcome["candidates"][0]["evidence"][0]["outcome"] = {}; variants.append(bad_outcome)
        for item in variants:
            with self.subTest(item=item), self.assertRaises(feedback.ValidationError):
                feedback.validate_data(item)

    def test_duplicate_candidate_ids_rejected(self):
        self.data["candidates"].append(copy.deepcopy(self.data["candidates"][0]))
        with self.assertRaises(feedback.ValidationError) as caught:
            feedback.validate_data(self.data)
        self.assertIn("duplicate candidate id", str(caught.exception))

    def test_build_hashes_and_no_overwrite(self):
        output = self.root / "bundle"
        manifest = feedback.build_bundle(self.data, output)
        self.assertEqual(sorted(p.name for p in output.iterdir()), ["feedback.json", "feedback.md", "manifest.json"])
        for name in ("feedback.json", "feedback.md"):
            payload = (output / name).read_bytes()
            self.assertEqual(manifest["files"][name]["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(manifest["files"][name]["bytes"], len(payload))
        self.assertEqual(json.loads((output / "manifest.json").read_text()), manifest)
        marker = (output / "feedback.md").read_bytes()
        with self.assertRaises(feedback.ValidationError):
            feedback.build_bundle(self.data, output)
        self.assertEqual((output / "feedback.md").read_bytes(), marker)

    def test_symlink_output_is_rejected(self):
        actual = self.root / "actual"
        actual.mkdir()
        linked = self.root / "linked"
        linked.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(feedback.ValidationError):
            feedback.build_bundle(self.data, linked)

    def test_symlink_in_output_ancestry_is_rejected(self):
        actual = self.root / "actual"
        (actual / "child").mkdir(parents=True)
        linked = self.root / "linked-parent"
        linked.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(feedback.ValidationError):
            feedback.build_bundle(self.data, linked / "child" / "bundle")

    def test_mkdir_race_never_removes_directory_not_owned(self):
        output = self.root / "raced"
        original_mkdir = os.mkdir

        def competing_create(path, mode=0o777):
            original_mkdir(path, mode)
            (Path(path) / "other-owner.txt").write_text("keep", encoding="utf-8")
            raise FileExistsError("simulated race")

        with patch.object(feedback.os, "mkdir", side_effect=competing_create):
            with self.assertRaises(FileExistsError):
                feedback.build_bundle(self.data, output)
        self.assertEqual((output / "other-owner.txt").read_text(encoding="utf-8"), "keep")

    def test_cli_errors_do_not_echo_secret_unknown_field_or_input_path(self):
        secret_key = "sk-abcdefghijklmnopqrstuv"
        self.data[secret_key] = "hidden"
        bad = self.root / "private-input.json"
        bad.write_text(json.dumps(self.data), encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPT), "validate", str(bad)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(secret_key, result.stderr)
        self.assertNotIn(str(bad), result.stderr)

    def test_render_escapes_markdown_metacharacters(self):
        self.data["candidates"][0]["trigger"] = "包含 * 星号与 [ 方括号"
        rendered = feedback.render_markdown(self.data)
        self.assertIn(r"包含 \* 星号与 \[ 方括号", rendered)


if __name__ == "__main__":
    unittest.main()
