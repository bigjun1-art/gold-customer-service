import importlib.util
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'knowledge_store.py'
spec = importlib.util.spec_from_file_location('store', SCRIPT)
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)


def contender(root, expected, value, start, results):
    start.wait()
    try:
        results.put(store.write_note(Path(root), 'rules.md', value, expected)['changed'])
    except ValueError:
        results.put(False)


class KnowledgeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_read_is_nonmutating(self):
        self.assertEqual(store.read_note(self.root, 'index.md')['sha256'], 'missing')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_write_backup_readback_and_noop(self):
        a = store.write_note(self.root, 'rules.md', '原规则', 'missing')
        b = store.write_note(self.root, 'rules.md', '新规则', a['sha256'])
        self.assertEqual(store.read_note(self.root, 'rules.md')['content'], '新规则')
        self.assertEqual(json.loads(Path(b['backup']).read_text())['content'], '原规则')
        self.assertFalse(store.write_note(self.root, 'rules.md', '新规则', b['sha256'])['changed'])
        self.assertEqual(len(list((self.root / '.history').iterdir())), 1)
        self.assertEqual((self.root / 'rules.md').stat().st_mode & 0o777, 0o600)

    def test_stale_update_cannot_overwrite(self):
        a = store.write_note(self.root, 'rules.md', 'A', 'missing')
        store.write_note(self.root, 'rules.md', 'B', a['sha256'])
        with self.assertRaises(ValueError):
            store.write_note(self.root, 'rules.md', 'C', a['sha256'])
        self.assertEqual((self.root / 'rules.md').read_text(), 'B')

    def test_path_escape_and_symlink_refused(self):
        (self.root / 'linked').symlink_to(self.root, target_is_directory=True)
        for target in ['../escape.md', '/tmp/escape.md', '.history/bad.md', 'linked/rules.md']:
            with self.subTest(target=target), self.assertRaises(ValueError):
                store.write_note(self.root, target, 'bad', 'missing')

    def test_interrupted_replace_preserves_old(self):
        a = store.write_note(self.root, 'rules.md', 'A', 'missing')
        with patch.object(store.os, 'replace', side_effect=OSError('simulated failure')):
            with self.assertRaises(OSError):
                store.write_note(self.root, 'rules.md', 'B', a['sha256'])
        self.assertEqual((self.root / 'rules.md').read_text(), 'A')
        self.assertEqual(list(self.root.glob('.pending-*')), [])

    def test_concurrent_writers_do_not_lose_update(self):
        a = store.write_note(self.root, 'rules.md', 'A', 'missing')
        ctx = multiprocessing.get_context('fork')
        start = ctx.Event(); results = ctx.Queue()
        processes = [ctx.Process(target=contender, args=(str(self.root), a['sha256'], value, start, results)) for value in ['B', 'C']]
        for process in processes: process.start()
        start.set()
        for process in processes:
            process.join(5)
            if process.is_alive(): process.terminate(); self.fail('Writer did not finish')
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(sum(results.get(timeout=1) for _ in processes), 1)
        self.assertIn((self.root / 'rules.md').read_text(), ['B', 'C'])


if __name__ == '__main__':
    unittest.main()
