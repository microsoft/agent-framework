"""Credential-free verifier boundaries, using mocked container operations."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pr_repair_worker import python_verify as tools
from pr_repair_worker import requested_verify as verify

PIN = "example/python@sha256:" + "d" * 64
DOTNET_PIN = "example/dotnet@sha256:" + "c" * 64
HEAD = "a" * 40
BASE = "b" * 40
IMAGE = "sha256:" + "f" * 64
PROJECT = "dotnet/tests/Example.UnitTests/Example.UnitTests.csproj"
FILES = {
    "dotnet/global.json": '{"sdk":{"version":"10.0.401"},"test":{"runner":"Microsoft.Testing.Platform"}}',
    PROJECT: "<Project />",
    "dotnet/tests/Example.UnitTests/Test.cs": "class Test {}",
}


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.files = dict(FILES)
        self.fail = lambda command: False

    def run_command(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command[0] == "git":
            return 0, tools._overlay(FILES)
        if command[:3] == ["docker", "image", "inspect"]:
            return 0, IMAGE.encode()
        if "/bin/tar" in command and "-cf" in command:
            group = command[-1]
            return 0, tools._overlay(
                {
                    p: text
                    for p, text in self.files.items()
                    if p == str(group) or p.startswith(str(group) + "/")
                }
            )
        return (1, b"compiler diagnostic") if self.fail(command) else (0, b"ok")

    def verify(self, **kwargs):
        with patch.object(tools, "_run", side_effect=self.run_command):
            return verify.verify_requested_revision(
                Path("/public"),
                HEAD,
                kwargs.pop("replacements", {}),
                trusted_sha=BASE,
                targets={"dotnet": [PROJECT]},
                images=kwargs.pop("images", {"python": PIN, "dotnet": DOTNET_PIN}),
                **kwargs,
            )

    def test_offline_source_order_and_mtp_commands(self):
        result = self.verify()
        self.assertTrue(result["passed"])
        self.assertTrue(result["checks_completed"])
        disconnect = next(
            i for i, (cmd, _) in enumerate(self.calls) if "disconnect" in cmd
        )
        copies = [
            i
            for i, (cmd, _) in enumerate(self.calls)
            if "/bin/tar" in cmd and "-xf" in cmd
        ]
        self.assertLess(copies[0], disconnect)
        self.assertGreater(copies[1], disconnect)
        self.assertEqual(result["images"], {"dotnet": IMAGE})
        test = result["commands"][1]
        self.assertIn("--project", test)
        self.assertNotIn("--filter", test)
        self.assertEqual(test[-3:], ["--", "--minimum-expected-tests", "1"])
        create = next(c for c, _ in self.calls if c[:2] == ["docker", "create"])
        self.assertIn("--env=GITHUB_ACTIONS=true", create)
        self.assertEqual(
            [item["kind"] for item in result["results"]], ["quality", "tests"]
        )

    def test_collects_all_failures_and_confirms_source(self):
        self.fail = lambda cmd: "build" in cmd
        result = self.verify()
        self.assertFalse(result["passed"])
        self.assertTrue(result["checks_completed"])
        self.assertTrue(result["source_unchanged"])
        self.assertEqual(len(result["results"]), 2)

    def test_setup_failure_is_not_diagnostic(self):
        self.fail = lambda cmd: "restore" in cmd
        result = self.verify()
        self.assertFalse(result["checks_started"])
        self.assertFalse(result["checks_completed"])
        self.assertEqual(result["results"], [])

    def test_changed_source_rejected_after_failed_check(self):
        def fail(cmd):
            if "build" in cmd:
                self.files["dotnet/tests/Example.UnitTests/Test.cs"] = (
                    "class Changed {}"
                )
                return True
            return False

        self.fail = fail
        result = self.verify()
        self.assertFalse(result["source_unchanged"])
        self.assertFalse(result["checks_completed"])

    def test_immutable_repository_images_used_for_pull(self):
        self.assertTrue(
            self.verify(images={"python": PIN, "dotnet": DOTNET_PIN})["passed"]
        )
        self.assertTrue(
            all(
                "@sha256:" in cmd[-1]
                for cmd, _ in self.calls
                if cmd[:2] == ["docker", "pull"]
            )
        )

    def test_python_delegates_collect_all(self):
        result = {
            "passed": True,
            "checks_started": True,
            "checks_completed": True,
            "source_unchanged": True,
            "commands": [],
            "results": [],
            "output": "",
            "image_id": IMAGE,
        }
        with patch.object(tools, "verify_revision", return_value=result) as call:
            verify.verify_requested_revision(
                Path("/public"),
                HEAD,
                {},
                trusted_sha=BASE,
                targets={"python": ["core"]},
                images={"python": PIN, "dotnet": DOTNET_PIN},
            )
        self.assertTrue(call.call_args.kwargs["collect_all"])

    def test_both_language_verifiers_receive_entire_candidate(self):
        changes = {
            "python/packages/core/example.py": "x = 1",
            "dotnet/src/Example/Example.cs": "class X {}",
        }
        result = {
            "passed": True,
            "checks_started": True,
            "checks_completed": True,
            "source_unchanged": True,
            "commands": [],
            "results": [],
            "output": "",
            "image_id": IMAGE,
        }
        with (
            patch.object(tools, "verify_revision", return_value=result) as python_call,
            patch.object(verify, "_dotnet_verify", return_value=result) as dotnet_call,
        ):
            verify.verify_requested_revision(
                Path("/public"),
                HEAD,
                changes,
                trusted_sha=BASE,
                targets={"python": ["core"], "dotnet": [PROJECT]},
                images={"python": PIN, "dotnet": DOTNET_PIN},
            )
        python_overlay = {
            **python_call.call_args.args[2],
            **python_call.call_args.kwargs["companion_replacements"],
        }
        self.assertEqual(python_overlay, changes)
        self.assertEqual(dotnet_call.call_args.args[2], changes)

    def test_dotnet_checks_hash_python_companion(self):
        path = "python/packages/core/example.py"
        with patch.dict(FILES, {path: "x = 0"}):
            self.files[path] = "x = 1"
            with patch.object(tools, "_run", side_effect=self.run_command):
                self.assertTrue(
                    verify._dotnet_verify(
                        Path("/public"),
                        HEAD,
                        {path: "x = 1"},
                        [PROJECT],
                        BASE,
                        DOTNET_PIN,
                    )["passed"]
                )

            def mutate(command):
                if "build" in command:
                    self.files[path] = "x = 2"
                return False

            self.fail = mutate
            with patch.object(tools, "_run", side_effect=self.run_command):
                self.assertFalse(
                    verify._dotnet_verify(
                        Path("/public"),
                        HEAD,
                        {path: "x = 1"},
                        [PROJECT],
                        BASE,
                        DOTNET_PIN,
                    )["source_unchanged"]
                )

    def test_rejects_unsupported_target_before_docker(self):
        for project in [
            "dotnet/tests/X.IntegrationTests/X.IntegrationTests.csproj",
            "../escape.csproj",
            "dotnet/src/missing.csproj",
        ]:
            with patch.object(tools, "_run", side_effect=self.run_command):
                result = verify.verify_requested_revision(
                    Path("/public"),
                    HEAD,
                    {},
                    trusted_sha=BASE,
                    targets={"dotnet": [project]},
                    images={"python": PIN, "dotnet": DOTNET_PIN},
                )
            self.assertFalse(result["passed"])
            self.assertFalse(result["checks_started"])
        self.assertFalse(any(cmd[0] == "docker" for cmd, _ in self.calls))


if __name__ == "__main__":
    unittest.main()
