"""Public worker schema, pinning, and container boundary tests without PR execution."""

import hashlib
import io
import json
import sys
import tarfile
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import verify_pr_repair as worker
from pr_repair_worker import python_verify as verify

SHA = "a" * 40
PIN = "example/runtime@sha256:" + "b" * 64
TOOLCHAIN = {key: PIN for key in ("python_image", "dotnet_image")}


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.checkout = Path(self.temp.name)
        (self.checkout / ".github").mkdir()
        (self.checkout / ".github/pr-repair-toolchain.json").write_text(
            json.dumps(TOOLCHAIN)
        )
        self.request = {
            "schema_version": 1,
            "repo": "microsoft/agent-framework",
            "automation_sha": SHA,
            "head_sha": SHA,
            "base_sha": "c" * 40,
            "snapshot_sha256": "d" * 64,
            "kind": "python",
            "packages": ["core"],
            "toolchain": dict(TOOLCHAIN),
            "replacements": {},
        }

    def validate(self, request=None, **kwargs):
        data = json.dumps(self.request if request is None else request).encode()
        with patch.object(verify, "_run", return_value=(0, SHA.encode())):
            return worker.validate_request(
                data,
                kwargs.get("digest", hashlib.sha256(data).hexdigest()),
                self.checkout,
                kwargs.get("repository", "microsoft/agent-framework"),
            )

    def test_valid_request(self):
        self.assertEqual(self.validate(), self.request)

    def test_bad_revision_digest_repo_or_schema_rejected(self):
        for key, value in [
            ("head_sha", "main"),
            ("schema_version", True),
            ("kind", "execute"),
            ("repo", "attacker/repository"),
            ("automation_sha", "f" * 40),
            ("snapshot_sha256", "no"),
            ("packages", ["../escape"]),
        ]:
            request = {**self.request, key: value}
            with self.assertRaises(ValueError):
                self.validate(request)
        with self.assertRaises(ValueError):
            self.validate(digest="f" * 64)

    def test_duplicate_keys_and_oversize_rejected(self):
        for data in [b'{"x":1,"x":2}', b" " * (worker.MAX_REQUEST + 1)]:
            with self.assertRaises(ValueError):
                worker._load(data)

    def test_toolchain_requires_exact_trusted_digest(self):
        for image in [
            "python:latest",
            "sha256:" + "a" * 64,
            "example/runtime@sha256:" + "e" * 64,
        ]:
            with self.assertRaises(ValueError):
                self.validate(
                    {**self.request, "toolchain": {**TOOLCHAIN, "python_image": image}}
                )

    def test_source_controls_not_accepted(self):
        for path in [
            "python/pyproject.toml",
            "dotnet/Directory.Build.props",
            "python/packages/core/../escape.py",
            "python//packages/core/a.py",
        ]:
            with self.assertRaises(ValueError):
                self.validate({**self.request, "replacements": {path: "x"}})

    def test_container_limits(self):
        limits = verify._container_limits()
        for expected in [
            "--user=65532:65532",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--ulimit=fsize=536870912:536870912",
            "--ulimit=nofile=1024:1024",
        ]:
            self.assertIn(expected, limits)
        self.assertTrue(
            any("nr_inodes=65536" in item and "size=3g" in item for item in limits)
        )
        self.assertTrue(
            any("nr_inodes=16384" in item and "size=512m" in item for item in limits)
        )
        self.assertNotIn("HOME", verify.PROCESS_ENV)
        self.assertNotIn("GH_TOKEN", verify.PROCESS_ENV)
        self.assertEqual(verify.PROCESS_ENV["GIT_CONFIG_GLOBAL"], "/dev/null")

    def test_owned_archive_clears_privileged_modes(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            info = tarfile.TarInfo("script.py")
            info.size = 1
            info.mode = 0o4777
            archive.addfile(info, io.BytesIO(b"x"))
        with tarfile.open(
            fileobj=io.BytesIO(verify._owned_archive(stream.getvalue()))
        ) as archive:
            info = archive.getmembers()[0]
            self.assertEqual((info.uid, info.gid, info.mode), (65532, 65532, 0o755))

    def test_fixed_tar_copy_uses_clean_environment(self):
        calls = []

        def run(command, **kwargs):
            calls.append((command, kwargs))
            return b""

        data = verify._overlay({"python/packages/core/a.py": "x = 1"})
        verify._copy_in("worker", "/work/source", data, run)
        with patch.object(
            verify,
            "_run",
            side_effect=lambda cmd, **kw: calls.append((cmd, kw)) or (0, data),
        ):
            verify._copy_out("worker", "python/packages")
        for command, kwargs in calls:
            index = command.index("/usr/bin/env")
            self.assertEqual(
                command[index : index + 5],
                ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "LANG=C", "/bin/tar"],
            )
            self.assertNotIn("sh", command)
        self.assertIn("--no-same-owner", calls[0][0])
        self.assertIn("--no-same-permissions", calls[0][0])
        self.assertTrue(calls[1][1]["binary"])
        self.assertEqual(calls[1][1]["limit"], verify.MAX_ARCHIVE)
        self.assertIn("--read-only", verify._container_limits())
        self.assertFalse(
            any("/work/tools" in option for option in verify._container_limits())
        )

    def test_transfer_rejects_unsupported_paths(self):
        with self.assertRaises(ValueError):
            verify._copy_in("worker", "/etc", b"", lambda *args, **kwargs: b"")
        with self.assertRaises(ValueError):
            verify._copy_out("worker", "../escape")

    def test_toolchain_contains_only_bundled_runtime_images(self):
        self.assertEqual(
            set(self.validate()["toolchain"]), {"python_image", "dotnet_image"}
        )
        with self.assertRaises(ValueError):
            self.validate({**self.request, "toolchain": {**TOOLCHAIN, "uv_image": PIN}})

    def test_no_raw_output_in_result(self):
        diagnostics = types.ModuleType("pr_repair_worker.diagnostics")
        diagnostics.extract_diagnostics = lambda text: (
            "sanitized diagnostic" if "diagnostic" in text else ""
        )
        result = {
            "passed": False,
            "checks_started": True,
            "checks_completed": True,
            "source_unchanged": True,
            "commands": [["ruff", "check"]],
            "output": "secret aggregate",
            "image_id": "local-id",
            "results": [
                {
                    "kind": "quality",
                    "passed": False,
                    "command": ["ruff", "check"],
                    "output": "secret diagnostic",
                }
            ],
        }
        with patch.dict(sys.modules, {"pr_repair_worker.diagnostics": diagnostics}):
            sanitized = worker.sanitize_result(result, self.request)
        self.assertNotIn("secret", json.dumps(sanitized))
        self.assertEqual(sanitized["image_id"], PIN)

    def test_public_fetch_uses_bare_repository_and_no_credentials(self):
        calls = []
        with patch.object(
            verify, "_run", side_effect=lambda cmd, **kw: calls.append(cmd) or (0, b"")
        ):
            worker._public_objects(
                "microsoft/agent-framework", [SHA], Path("/tmp/source")
            )
        self.assertEqual(calls[0][:3], ["git", "init", "--bare"])
        self.assertIn("credential.helper=", calls[1])
        self.assertFalse(any("checkout" in cmd for cmd in calls))


if __name__ == "__main__":
    unittest.main()
