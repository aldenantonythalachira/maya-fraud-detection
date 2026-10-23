import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("versions", Path(__file__).resolve().parents[1] / "scripts/versions.py")
versions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(versions)


class VersionTests(unittest.TestCase):
    def test_restore_preserves_newer_branch_and_refuses_dirty_work(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
            git("init", "-b", "feature")
            git("config", "user.email", "test@example.invalid")
            git("config", "user.name", "Checkpoint test")
            source = root / "example.txt"
            source.write_text("first", encoding="utf-8")
            git("add", "example.txt")
            git("commit", "-m", "first")
            first = git("rev-parse", "HEAD")
            with patch.object(versions, "ROOT", root), patch.object(sys, "argv", ["versions.py", "save", "test"]):
                versions.main()
            source.write_text("second", encoding="utf-8")
            with patch.object(versions, "ROOT", root), patch.object(sys, "argv", ["versions.py", "restore", "test"]):
                with self.assertRaisesRegex(SystemExit, "Local changes"):
                    versions.main()
            self.assertEqual(source.read_text(), "second")
            git("add", "example.txt")
            git("commit", "-m", "second")
            second = git("rev-parse", "HEAD")
            with patch.object(versions, "ROOT", root), patch.object(sys, "argv", ["versions.py", "restore", "test"]):
                versions.main()
            self.assertEqual(git("rev-parse", "HEAD"), first)
            self.assertEqual(git("rev-parse", "feature"), second)
            self.assertEqual(source.read_text(), "first")
