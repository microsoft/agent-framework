"""Verifier boundary tests; never start Docker or execute PR code."""

import io
import subprocess
import sys
import tarfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pr_repair_worker import python_verify as verify

PIN = "example/python@sha256:" + "d" * 64
DOTNET_PIN = "example/dotnet@sha256:" + "c" * 64
HEAD = "a" * 40
BASE = "b" * 40
FILES = {
    "python/packages/core/pyproject.toml": '[project]\nname="core"',
    "python/packages/core/tests/test_core.py": "pass",
    "python/packages/core/core.py": "pass",
}


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.files = dict(FILES)
        self.failure = None
        self.copied_sources = []

    def run_command(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command[0] == "git":
            files = dict(FILES)
            if command[-1] == BASE:
                files["python/packages/core/core.py"] = "trusted = True"
            return 0, verify._overlay(files)
        if command[:3] == ["docker", "image", "inspect"]:
            return 0, b"sha256:" + b"f" * 64
        if "/bin/tar" in command and "-cf" in command:
            group = command[-1]
            return 0, verify._overlay(
                {
                    k: v
                    for k, v in self.files.items()
                    if k == group or k.startswith(group + "/")
                }
            )
        if self.failure and self.failure(command):
            return 1, b"failed"
        return 0, b"ok"

    def verify(
        self, replacements=None, packages=None, collect_all=False, companions=None
    ):
        with patch.object(verify, "_run", side_effect=self.run_command):
            return verify.verify_revision(
                Path("/public"),
                HEAD,
                replacements or {},
                ["core"] if packages is None else packages,
                trusted_sha=BASE,
                image=PIN,
                collect_all=collect_all,
                companion_replacements=companions,
            )

    def test_isolation_and_trusted_dependency_order(self):
        result = self.verify()
        self.assertTrue(result["passed"])
        self.assertTrue(result["checks_started"])
        self.assertEqual(result["image_id"], "sha256:" + "f" * 64)
        self.assertEqual(len(result["commands"]), 5)
        self.assertTrue(
            any("/work:rw,exec," in option for option in verify._container_limits())
        )
        self.assertIn("--check", result["commands"][0])
        self.assertFalse(any("check-packages" in c for c in result["commands"]))
        create = next(c for c, _ in self.calls if c[:2] == ["docker", "create"])
        for flag in [
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--env=UV_PROJECT_ENVIRONMENT=/work/venv",
            "sha256:" + "f" * 64,
        ]:
            self.assertIn(flag, create)
        for flag in ["--mount", "-v", "--privileged"]:
            self.assertNotIn(flag, create)
        disconnect = next(
            i
            for i, (c, _) in enumerate(self.calls)
            if c[:3] == ["docker", "network", "disconnect"]
        )
        copies = [
            (i, kw["data"])
            for i, (c, kw) in enumerate(self.calls)
            if "/bin/tar" in c and "-xf" in c
        ]
        self.assertLess(copies[0][0], disconnect)
        self.assertGreater(copies[1][0], disconnect)
        self.assertNotEqual(copies[0][1], copies[1][1])
        self.assertEqual(self.calls[-1][0][:3], ["docker", "rm", "--force"])
        self.assertNotIn("GH_TOKEN", verify.PROCESS_ENV)
        self.assertNotIn("HOME", verify.PROCESS_ENV)

    def test_missing_package_is_not_skipped(self):
        result = self.verify(packages=["missing"])
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks_started"])
        self.assertEqual(len(self.calls), 1)

    def test_generated_root_caches_are_not_exported(self):
        self.files["python/.mypy_cache/cache.json"] = "generated cache"
        self.files["python/.pytest_cache/state.json"] = "generated cache"
        result = self.verify()
        self.assertTrue(result["passed"])
        exports = [c[-1] for c, _ in self.calls if "/bin/tar" in c and "-cf" in c]
        self.assertTrue(exports)
        self.assertTrue(all(path == "python/packages" for path in exports))

    def test_new_python_file_in_source_group_is_rejected(self):
        self.files["python/packages/core/unexpected.py"] = "generated = True"
        self.assertFalse(self.verify()["passed"])

    def test_source_groups_cover_scripts_and_root_files(self):
        additions = {
            "root.py": "root = True",
            "python/root.py": "root = True",
            "python/scripts/task.py": "task = True",
            ".github/scripts/task.py": "task = True",
        }
        with patch.dict(FILES, additions):
            self.files.update(additions)
            self.assertTrue(self.verify()["passed"])

    def test_invalid_selection_is_rejected_without_commands(self):
        for packages in [[], ["../core"], ["core;env"], ["*"]]:
            self.calls.clear()
            self.assertFalse(self.verify(packages=packages)["passed"])
            self.assertFalse(self.calls)

    def test_rejects_unsafe_archive_entries(self):
        for name, kind in [
            ("escape", tarfile.SYMTYPE),
            ("hard", tarfile.LNKTYPE),
            ("device", tarfile.CHRTYPE),
            ("../escape", tarfile.REGTYPE),
            ("/absolute", tarfile.REGTYPE),
            (".git/config", tarfile.REGTYPE),
        ]:
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w") as tar:
                item = tarfile.TarInfo(name)
                item.type = kind
                tar.addfile(item)
            with self.assertRaises(ValueError):
                verify._validate_archive(stream.getvalue())

    def test_rejects_replacements_outside_source(self):
        for path in [
            "python/pyproject.toml",
            "python/packages/core/new.py",
            "../escape.py",
        ]:
            self.calls.clear()
            self.assertFalse(self.verify({path: "pass"})["passed"])
            self.assertEqual(len(self.calls), 1)

    def test_network_failure_never_loads_pr_or_starts_checks(self):
        self.failure = lambda c: c[:3] == ["docker", "network", "disconnect"]
        result = self.verify()
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks_started"])
        self.assertEqual(
            sum("/bin/tar" in c and "-xf" in c for c, _ in self.calls),
            1,
        )
        self.assertEqual(self.calls[-1][0][:3], ["docker", "rm", "--force"])

    def test_detects_formatter_modifications(self):
        def modify(command):
            if "format" in command:
                self.files["python/packages/core/core.py"] = "changed = True"
            return False

        self.failure = modify
        result = self.verify()
        self.assertFalse(result["passed"])
        self.assertTrue(result["checks_started"])

    def test_accepts_validated_replacement_hash(self):
        self.files["python/packages/core/core.py"] = "x: int = 1"
        self.assertTrue(
            self.verify({"python/packages/core/core.py": "x: int = 1"})["passed"]
        )

    def test_check_failure_marks_checks_started(self):
        self.failure = lambda c: "format" in c
        result = self.verify()
        self.assertFalse(result["passed"])
        self.assertTrue(result["checks_started"])

    def test_collect_all_preserves_diagnostics_after_failure(self):
        self.failure = lambda command: "format" in command
        result = self.verify(collect_all=True)
        self.assertFalse(result["passed"])
        self.assertTrue(result["checks_completed"])
        self.assertTrue(result["source_unchanged"])
        self.assertEqual(
            [item["kind"] for item in result["results"]],
            ["quality", "quality", "quality", "typing", "tests"],
        )
        self.assertEqual(
            [item["passed"] for item in result["results"]],
            [False, True, True, True, True],
        )

    def test_fail_fast_still_checks_source(self):
        def modify(command):
            if "format" in command:
                self.files["python/packages/core/core.py"] = "changed = True"
                return True
            return False

        self.failure = modify
        result = self.verify()
        self.assertFalse(result["passed"])
        self.assertFalse(result["source_unchanged"])
        self.assertFalse(result["checks_completed"])
        self.assertEqual(len(result["results"]), 1)

    def test_python_checks_overlay_and_hash_csharp_companion(self):
        path = "dotnet/src/Example/File.cs"
        with patch.dict(FILES, {path: "class Original {}"}):
            self.files[path] = "class Candidate {}"
            result = self.verify(companions={path: self.files[path]})
            self.assertTrue(result["passed"])
            overlays = [
                kwargs["data"]
                for cmd, kwargs in self.calls
                if "/bin/tar" in cmd and "-xf" in cmd
            ]
            self.assertIn(path, verify._validate_archive(overlays[-1]))

            def mutate(command):
                if "format" in command:
                    self.files[path] = "class ChangedDuringChecks {}"
                return False

            self.failure = mutate
            result = self.verify(companions={path: "class Candidate {}"})
            self.assertFalse(result["passed"])
            self.assertFalse(result["source_unchanged"])

    def test_companion_cannot_replace_controls_or_overlap(self):
        for companions in [
            {"python/packages/core/pyproject.toml": ""},
            {"python/packages/core/core.py": "pass"},
            {"dotnet/src/New.cs": "class New {}"},
        ]:
            self.assertFalse(
                self.verify(
                    {"python/packages/core/core.py": "pass"}, companions=companions
                )["passed"]
            )

    def test_output_is_bounded(self):
        code, output = verify._run(
            [sys.executable, "-c", 'print("x" * 100000)'], limit=100
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(output), 100)
        with self.assertRaises(ValueError):
            verify._run(
                [sys.executable, "-c", 'print("x" * 10000)'], limit=100, binary=True
            )

    def test_timeout_is_enforced(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            verify._run(
                [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.05
            )


if __name__ == "__main__":
    unittest.main()
