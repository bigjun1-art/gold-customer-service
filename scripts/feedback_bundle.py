#!/usr/bin/env python3
"""Validate, render, and package distilled customer-service feedback."""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys


OUTCOMES = {"resolved", "unresolved", "escalated", "abandoned", "unknown"}
RESULTS = {"pass", "partial", "fail", "unknown"}
CONCLUSIONS = {"improved", "no_change", "regressed", "inconclusive"}
TARGET_TYPES = {"knowledge_id", "reference_path"}
STATUS = {"unverified", "verified"}
ID_RE = re.compile(r"^[a-z][a-z0-9._-]{2,63}$")
FEEDBACK_ID_RE = re.compile(r"^fb-v1-[a-z0-9][a-z0-9._-]{7,63}$")
SKILL_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?$")
CASE_ID_RE = re.compile(r"^case-[a-z0-9][a-z0-9_-]{2,63}$")
TURN_RE = re.compile(r"^turn-[1-9][0-9]*(?:-[1-9][0-9]*)?$")
SCOPE_RE = re.compile(r"^scope-[a-z0-9][a-z0-9-]{2,63}$")
KNOWLEDGE_ID_RE = re.compile(r"^(?:knowledge:[a-z0-9][a-z0-9._/-]{2,95}|M-[A-Z]{2,8}[0-9]{0,4})$")
REFERENCE_PATH_RE = re.compile(r"^references/[a-z0-9][a-z0-9_-]*\.md$")
METHOD_PATH_RE = re.compile(r"^knowledge/methods/[A-Za-z0-9][A-Za-z0-9_-]*\.md$")
REFERENCE_PATHS = {
    "references/data-diagnostics.md",
    "references/design-sources.md",
    "references/distillation.md",
    "references/ingestion.md",
    "references/operations.md",
    "references/quality.md",
    "references/service.md",
    "references/source-review.md",
}

ROOT_KEYS = {
    "schema_version", "skill_version", "feedback_id", "synthetic", "period",
    "scope", "source_stats", "candidates", "privacy_reviewed", "share_authorized",
}
PERIOD_KEYS = {"start", "end"}
SOURCE_KEYS = {"conversation_count", "included_case_count", "missing_count", "missing_reasons", "notes"}
CANDIDATE_KEYS = {
    "id", "status", "target", "trigger", "proposed_change", "rationale",
    "evidence", "counterexamples", "evaluation",
}
TARGET_KEYS = {"type", "value"}
EVIDENCE_KEYS = {"case_id", "turns", "redacted_summary", "outcome"}
COUNTEREXAMPLE_KEYS = {"case_id", "redacted_summary", "outcome"}
EVALUATION_KEYS = {
    "training_case_ids", "heldout_case_ids", "baseline_result",
    "candidate_result", "conclusion", "notes",
}

INJECTION_PATTERNS = [
    ("html", re.compile(r"<\s*(?:/?\s*[a-zA-Z]|!--|\?)[^>]*>")),
    ("markdown_image", re.compile(r"!\s*\[[^\]]*\]\s*\(")),
    ("markdown_link", re.compile(r"(?<!!)\[[^\]]+\]\s*\(\s*(?:https?|ftp|file|data):", re.I)),
    ("external_url", re.compile(r"(?:https?|ftp|file|data)://|\bwww\.", re.I)),
]
PRIVACY_PATTERNS = [
    ("email", re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?!\w)", re.I)),
    ("phone", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")),
    ("identity_number", re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")),
    ("local_path", re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\\\)[^\s]+")),
    ("secret", re.compile(r"(?:\bsk-[A-Za-z0-9_-]{16,}|\bAKIA[0-9A-Z]{16}\b|\bBearer\s+[A-Za-z0-9._~+/-]{12,}|\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,})", re.I)),
]


class ValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def _exact_object(value, keys, location, errors):
    if not isinstance(value, dict):
        errors.append(f"{location}: expected object")
        return False
    missing = keys - value.keys()
    extra = value.keys() - keys
    for key in sorted(missing):
        errors.append(f"{location}.{key}: missing field")
    if extra:
        errors.append(f"{location}: {len(extra)} unexpected field(s)")
    return not missing and not extra


def _string(value, location, errors, *, minimum=1, maximum=1000, pattern=None):
    if not isinstance(value, str):
        errors.append(f"{location}: expected string")
        return False
    if not minimum <= len(value) <= maximum:
        errors.append(f"{location}: length must be {minimum}..{maximum}")
        return False
    if pattern and not pattern.fullmatch(value):
        errors.append(f"{location}: invalid format")
        return False
    return True


def _date(value, location, errors):
    if not _string(value, location, errors, maximum=10):
        return None
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        errors.append(f"{location}: expected YYYY-MM-DD calendar date")
        return None
    if parsed.isoformat() != value:
        errors.append(f"{location}: expected canonical YYYY-MM-DD")
        return None
    return parsed


def _case_ids(value, location, errors):
    if not isinstance(value, list):
        errors.append(f"{location}: expected array")
        return []
    if len(value) != len(set(value)) if all(isinstance(x, str) for x in value) else False:
        errors.append(f"{location}: duplicate case id")
    for index, case_id in enumerate(value):
        _string(case_id, f"{location}[{index}]", errors, maximum=69, pattern=CASE_ID_RE)
    return [case_id for case_id in value if isinstance(case_id, str)]


def _walk_strings(value, location="$", *, include_keys=False):
    if isinstance(value, str):
        yield location, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_strings(item, f"{location}[{index}]", include_keys=include_keys)
    elif isinstance(value, dict):
        for key, item in value.items():
            if include_keys:
                yield f"{location}.<key>", str(key)
            yield from _walk_strings(item, f"{location}.{key}", include_keys=include_keys)


def scan_privacy(data):
    """Return locations and finding types only; never include matched values."""
    findings = []
    for location, value in _walk_strings(data, include_keys=True):
        for finding_type, pattern in PRIVACY_PATTERNS:
            if pattern.search(value):
                findings.append({"location": location, "type": finding_type})
    return findings


def validate_data(data):
    errors = []
    if not _exact_object(data, ROOT_KEYS, "$", errors):
        raise ValidationError(errors)
    if data["schema_version"] != 1:
        errors.append("$.schema_version: only version 1 is supported")
    _string(data["skill_version"], "$.skill_version", errors, maximum=64, pattern=SKILL_VERSION_RE)
    _string(data["feedback_id"], "$.feedback_id", errors, maximum=70, pattern=FEEDBACK_ID_RE)
    if not isinstance(data["synthetic"], bool):
        errors.append("$.synthetic: expected boolean")
    if _exact_object(data["period"], PERIOD_KEYS, "$.period", errors):
        start = _date(data["period"]["start"], "$.period.start", errors)
        end = _date(data["period"]["end"], "$.period.end", errors)
        if start and end and start > end:
            errors.append("$.period: start must not be after end")
    _string(data["scope"], "$.scope", errors, maximum=70, pattern=SCOPE_RE)
    if _exact_object(data["source_stats"], SOURCE_KEYS, "$.source_stats", errors):
        stats = data["source_stats"]
        for key in ("conversation_count", "included_case_count", "missing_count"):
            if isinstance(stats[key], bool) or not isinstance(stats[key], int) or stats[key] < 0:
                errors.append(f"$.source_stats.{key}: expected non-negative integer")
        if all(isinstance(stats[k], int) and not isinstance(stats[k], bool) for k in ("conversation_count", "included_case_count", "missing_count")):
            if stats["included_case_count"] + stats["missing_count"] != stats["conversation_count"]:
                errors.append("$.source_stats: included_case_count + missing_count must equal conversation_count")
        if not isinstance(stats["missing_reasons"], list):
            errors.append("$.source_stats.missing_reasons: expected array")
        else:
            for index, reason in enumerate(stats["missing_reasons"]):
                _string(reason, f"$.source_stats.missing_reasons[{index}]", errors, maximum=240)
            if isinstance(stats.get("missing_count"), int) and not isinstance(stats.get("missing_count"), bool) and stats["missing_count"] == 0 and stats["missing_reasons"]:
                errors.append("$.source_stats.missing_reasons: must be empty when missing_count is zero")
            if isinstance(stats.get("missing_count"), int) and not isinstance(stats.get("missing_count"), bool) and stats["missing_count"] > 0 and not stats["missing_reasons"]:
                errors.append("$.source_stats.missing_reasons: required when records are missing")
        if not isinstance(stats["notes"], list):
            errors.append("$.source_stats.notes: expected array")
        else:
            for index, note in enumerate(stats["notes"]):
                _string(note, f"$.source_stats.notes[{index}]", errors, maximum=240)
    if not isinstance(data["privacy_reviewed"], bool):
        errors.append("$.privacy_reviewed: expected boolean")
    if not isinstance(data["share_authorized"], bool):
        errors.append("$.share_authorized: expected boolean")
    candidates = data["candidates"]
    if not isinstance(candidates, list) or not candidates:
        errors.append("$.candidates: expected non-empty array")
        candidates = []
    candidate_ids = []
    all_training_cases = set()
    all_heldout_cases = set()
    all_source_cases = set()
    for index, candidate in enumerate(candidates):
        base = f"$.candidates[{index}]"
        if not _exact_object(candidate, CANDIDATE_KEYS, base, errors):
            continue
        if _string(candidate["id"], f"{base}.id", errors, maximum=64, pattern=ID_RE):
            candidate_ids.append(candidate["id"])
        if not isinstance(candidate["status"], str) or candidate["status"] not in STATUS:
            errors.append(f"{base}.status: expected one of {sorted(STATUS)}")
        if _exact_object(candidate["target"], TARGET_KEYS, f"{base}.target", errors):
            target_type = candidate["target"]["type"]
            target_value = candidate["target"]["value"]
            if not isinstance(target_type, str) or target_type not in TARGET_TYPES:
                errors.append(f"{base}.target.type: expected one of {sorted(TARGET_TYPES)}")
            elif target_type == "knowledge_id":
                _string(target_value, f"{base}.target.value", errors, maximum=105, pattern=KNOWLEDGE_ID_RE)
            else:
                reference_ok = _string(target_value, f"{base}.target.value", errors, maximum=120)
                if reference_ok and not (REFERENCE_PATH_RE.fullmatch(target_value) and target_value in REFERENCE_PATHS) and not METHOD_PATH_RE.fullmatch(target_value):
                    errors.append(f"{base}.target.value: path is not an approved method reference")
        for key, maximum in (("trigger", 500), ("proposed_change", 1200), ("rationale", 800)):
            _string(candidate[key], f"{base}.{key}", errors, maximum=maximum)
        evidence = candidate["evidence"]
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{base}.evidence: expected non-empty array")
            evidence = []
        evidence_cases = []
        for e_index, item in enumerate(evidence):
            ebase = f"{base}.evidence[{e_index}]"
            if not _exact_object(item, EVIDENCE_KEYS, ebase, errors):
                continue
            if _string(item["case_id"], f"{ebase}.case_id", errors, maximum=69, pattern=CASE_ID_RE):
                evidence_cases.append(item["case_id"])
            if not isinstance(item["turns"], list) or not item["turns"]:
                errors.append(f"{ebase}.turns: expected non-empty array")
            else:
                for t_index, turn in enumerate(item["turns"]):
                    _string(turn, f"{ebase}.turns[{t_index}]", errors, maximum=30, pattern=TURN_RE)
            _string(item["redacted_summary"], f"{ebase}.redacted_summary", errors, maximum=500)
            if not isinstance(item["outcome"], str) or item["outcome"] not in OUTCOMES:
                errors.append(f"{ebase}.outcome: expected one of {sorted(OUTCOMES)}")
        supporting_cases = set(evidence_cases)
        counterexamples = candidate["counterexamples"]
        if not isinstance(counterexamples, list):
            errors.append(f"{base}.counterexamples: expected array")
            counterexamples = []
        for c_index, item in enumerate(counterexamples):
            cbase = f"{base}.counterexamples[{c_index}]"
            if not _exact_object(item, COUNTEREXAMPLE_KEYS, cbase, errors):
                continue
            if _string(item["case_id"], f"{cbase}.case_id", errors, maximum=69, pattern=CASE_ID_RE):
                evidence_cases.append(item["case_id"])
            _string(item["redacted_summary"], f"{cbase}.redacted_summary", errors, maximum=500)
            if not isinstance(item["outcome"], str) or item["outcome"] not in OUTCOMES:
                errors.append(f"{cbase}.outcome: expected one of {sorted(OUTCOMES)}")
        evaluation = candidate["evaluation"]
        if _exact_object(evaluation, EVALUATION_KEYS, f"{base}.evaluation", errors):
            training = _case_ids(evaluation["training_case_ids"], f"{base}.evaluation.training_case_ids", errors)
            heldout = _case_ids(evaluation["heldout_case_ids"], f"{base}.evaluation.heldout_case_ids", errors)
            if set(training) & set(heldout):
                errors.append(f"{base}.evaluation: training and heldout case ids must not overlap")
            if not set(evidence_cases).issubset(set(training)):
                errors.append(f"{base}.evaluation: every evidence and counterexample case must be in training_case_ids")
            if set(evidence_cases) & set(heldout):
                errors.append(f"{base}.evaluation: evidence and counterexample cases cannot be held out")
            all_training_cases.update(case for case in training if isinstance(case, str))
            all_heldout_cases.update(case for case in heldout if isinstance(case, str))
            all_source_cases.update(case for case in training + heldout if isinstance(case, str))
            for key in ("baseline_result", "candidate_result"):
                if not isinstance(evaluation[key], str) or evaluation[key] not in RESULTS:
                    errors.append(f"{base}.evaluation.{key}: expected one of {sorted(RESULTS)}")
            if not isinstance(evaluation["conclusion"], str) or evaluation["conclusion"] not in CONCLUSIONS:
                errors.append(f"{base}.evaluation.conclusion: expected one of {sorted(CONCLUSIONS)}")
            _string(evaluation["notes"], f"{base}.evaluation.notes", errors, minimum=0, maximum=600)
            if evaluation["conclusion"] == "improved":
                ranks = {"fail": 0, "partial": 1, "pass": 2}
                baseline = evaluation["baseline_result"]
                proposed = evaluation["candidate_result"]
                if not heldout or baseline == "unknown" or proposed == "unknown" or ranks.get(proposed, -1) <= ranks.get(baseline, -1):
                    errors.append(f"{base}.evaluation: improved requires a non-empty heldout set and a better known candidate result")
            if (not heldout or evaluation["baseline_result"] == "unknown" or evaluation["candidate_result"] == "unknown") and evaluation["conclusion"] != "inconclusive":
                errors.append(f"{base}.evaluation: missing or unknown evaluation requires inconclusive conclusion")
        if len(supporting_cases) <= 1 and candidate["status"] == "verified":
            errors.append(f"{base}.status: a single-case candidate must remain unverified")
        if candidate["status"] == "verified" and candidate["evaluation"].get("conclusion") == "inconclusive":
            errors.append(f"{base}.status: verified requires a conclusive heldout evaluation")
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("$.candidates: duplicate candidate id")
    if all_training_cases & all_heldout_cases:
        errors.append("$.candidates: a case cannot be training in one candidate and held out in another")
    included_count = data["source_stats"].get("included_case_count") if isinstance(data["source_stats"], dict) else None
    if isinstance(included_count, int) and not isinstance(included_count, bool) and len(all_source_cases) > included_count:
        errors.append("$.source_stats.included_case_count: fewer than the unique source case ids used by candidates")
    for location, value in _walk_strings(data):
        for finding_type, pattern in INJECTION_PATTERNS:
            if pattern.search(value):
                errors.append(f"{location}: forbidden {finding_type}")
    findings = scan_privacy(data)
    if findings:
        errors.extend(f"{item['location']}: possible {item['type']}" for item in findings)
    if errors:
        raise ValidationError(errors)
    ready = data["privacy_reviewed"] is True and data["share_authorized"] is True
    return {"valid": True, "ready": ready, "status": "ready" if ready else "not_ready", "privacy_findings": [], "notice": "Heuristic privacy checks are not an anonymization guarantee and may miss names; user review is required. Only distilled content is accepted, never raw conversations."}


def _escape(text):
    text = text.replace("\r", " ").replace("\n", " ")
    return re.sub(r"([\\`*_{}\[\]()#+.!|<>-])", r"\\\1", text)


def render_markdown(data):
    validate_data(data)
    lines = [
        "# 客服技能反馈包",
        "",
        f"- 反馈编号：{_escape(data['feedback_id'])}",
        f"- 技能版本：{_escape(data['skill_version'])}",
        f"- 周期：{_escape(data['period']['start'])} 至 {_escape(data['period']['end'])}",
        f"- 范围代号：{_escape(data['scope'])}",
        f"- 数据属性：{'合成示例' if data['synthetic'] else '提炼反馈'}",
        f"- 分享准备：{'已就绪' if data['privacy_reviewed'] and data['share_authorized'] else '未就绪'}",
        "",
        "## 来源统计",
        "",
        f"会话总数：{data['source_stats']['conversation_count']}；纳入案例：{data['source_stats']['included_case_count']}；缺失：{data['source_stats']['missing_count']}。",
    ]
    if data["source_stats"]["missing_reasons"]:
        lines.extend(["", "缺失原因："])
        lines.extend(f"- {_escape(reason)}" for reason in data["source_stats"]["missing_reasons"])
    for candidate in data["candidates"]:
        evaluation = candidate["evaluation"]
        lines.extend([
            "", f"## 候选改进：{_escape(candidate['id'])}", "",
            f"- 状态：{_escape(candidate['status'])}",
            f"- 目标：{_escape(candidate['target']['type'])} / {_escape(candidate['target']['value'])}",
            f"- 触发条件：{_escape(candidate['trigger'])}",
            f"- 建议变更：{_escape(candidate['proposed_change'])}",
            f"- 理由：{_escape(candidate['rationale'])}",
            "", "### 证据", "",
        ])
        for item in candidate["evidence"]:
            turns = "、".join(_escape(turn) for turn in item["turns"])
            lines.append(f"- {_escape(item['case_id'])}（{turns}；{_escape(item['outcome'])}）：{_escape(item['redacted_summary'])}")
        lines.extend(["", "### 反例", ""])
        if candidate["counterexamples"]:
            for item in candidate["counterexamples"]:
                lines.append(f"- {_escape(item['case_id'])}（{_escape(item['outcome'])}）：{_escape(item['redacted_summary'])}")
        else:
            lines.append("- 无已记录反例")
        lines.extend([
            "", "### 评估", "",
            f"- 训练案例：{_escape('、'.join(evaluation['training_case_ids'])) if evaluation['training_case_ids'] else '无'}",
            f"- 独立案例：{_escape('、'.join(evaluation['heldout_case_ids'])) if evaluation['heldout_case_ids'] else '无'}",
            f"- 基线结果：{_escape(evaluation['baseline_result'])}",
            f"- 候选结果：{_escape(evaluation['candidate_result'])}",
            f"- 结论：{_escape(evaluation['conclusion'])}",
            f"- 备注：{_escape(evaluation['notes']) if evaluation['notes'] else '无'}",
        ])
    lines.extend(["", "> 隐私扫描是启发式检查，不构成匿名化保证，也可能漏检姓名。用户必须复核。本包只接受人工提炼的内容，不接受原始对话。", ""])
    return "\n".join(lines)


def _canonical_json(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def build_bundle(data, output):
    result = validate_data(data)
    if not result["ready"]:
        raise ValidationError(["$: privacy_reviewed and share_authorized must both be true before build"])
    output = Path(output).absolute()
    if os.path.lexists(output):
        raise ValidationError(["output: path already exists; overwrite is refused"])
    parent = output.parent
    if not parent.is_dir() or any(ancestor.is_symlink() for ancestor in (parent, *parent.parents)):
        raise ValidationError(["output: parent must be an existing non-symlink directory"])
    json_bytes = _canonical_json(data)
    markdown_bytes = render_markdown(data).encode("utf-8")
    manifest = {
        "schema_version": 1,
        "feedback_id": data["feedback_id"],
        "files": {
            "feedback.json": {"sha256": _sha256(json_bytes), "bytes": len(json_bytes)},
            "feedback.md": {"sha256": _sha256(markdown_bytes), "bytes": len(markdown_bytes)},
        },
    }
    created_owned = False
    try:
        os.mkdir(output, 0o700)
        created_owned = True
        for name, payload in (("feedback.json", json_bytes), ("feedback.md", markdown_bytes), ("manifest.json", _canonical_json(manifest))):
            descriptor = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
    except Exception:
        if created_owned and output.is_dir() and not output.is_symlink():
            shutil.rmtree(output)
        raise
    return manifest


def load_json(path):
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except json.JSONDecodeError as exc:
        raise ValidationError([f"input: invalid JSON at line {exc.lineno}, column {exc.colno}"]) from None
    except (OSError, UnicodeError):
        raise ValidationError(["input: unable to read UTF-8 JSON file"]) from None
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("json_file", type=Path)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("json_file", type=Path)
    build_parser.add_argument("--output", type=Path, required=True)
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("json_file", type=Path)
    args = parser.parse_args(argv)
    try:
        data = load_json(args.json_file)
        if args.command == "validate":
            print(json.dumps(validate_data(data), ensure_ascii=False, sort_keys=True))
        elif args.command == "render":
            sys.stdout.write(render_markdown(data))
        else:
            manifest = build_bundle(data, args.output)
            print(json.dumps({"built": True, "output": str(args.output), "manifest": manifest}, ensure_ascii=False, sort_keys=True))
        return 0
    except ValidationError as exc:
        print(json.dumps({"valid": False, "errors": exc.errors, "notice": "Heuristic privacy checks are not an anonymization guarantee and may miss names; user review is required. Input must contain distilled content only, never raw conversations."}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1
    except (OSError, UnicodeError, TypeError, KeyError):
        print(json.dumps({"valid": False, "errors": ["operation failed without exposing input content or local paths"], "notice": "Heuristic privacy checks are not an anonymization guarantee and may miss names; user review is required. Input must contain distilled content only, never raw conversations."}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
