# Copyright (c) Microsoft. All rights reserved.

"""Offline regression tests, also runnable with the standard-library unittest runner."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.dependencies.detect_version_bumps import changed_package_versions, main


class VersionBumpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "--quiet")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        self.git("config", "commit.gpgsign", "false")
        self.write(
            "python/pyproject.toml",
            '[project]\nname = "agent-framework"\nversion = "1.0.0"\n'
            '[tool.uv.workspace]\nmembers = ["packages/*"]\nexclude = ["packages/lab"]\n',
        )
        self.write("python/packages/core/pyproject.toml", '[project]\nversion = "1.0.0"\n')
        self.write("python/packages/provider/pyproject.toml", '[project]\nversion = "1.0.0b1"\n')
        self.write("python/packages/lab/pyproject.toml", '[project]\nversion = "1.0.0a1"\n')
        self.commit()
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True).stdout

    def write(self, name: str, content: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def commit(self) -> None:
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Test snapshot")

    def test_unchanged_tree_skips(self) -> None:
        self.assertEqual(changed_package_versions(self.root, self.base), [])

    def test_metadata_dependencies_and_tool_versions_do_not_trigger(self) -> None:
        self.write(
            "python/packages/core/pyproject.toml",
            '[project]\nversion = "1.0.0"\ndescription = "changed"\ndependencies = ["example>=2"]\n'
            '[tool.example]\nversion = "9"\n',
        )
        self.commit()
        self.assertEqual(changed_package_versions(self.root, self.base), [])

    def test_toml_formatting_does_not_trigger(self) -> None:
        self.write("python/packages/core/pyproject.toml", "[project]\nversion='1.0.0' # comment\n")
        self.commit()
        self.assertEqual(changed_package_versions(self.root, self.base), [])

    def test_package_version_changes_trigger(self) -> None:
        for version in ("1.0.0b2", "1.0.0rc1", "1.0.0", "0.9.0"):
            with self.subTest(version=version):
                self.write("python/packages/provider/pyproject.toml", f'[project]\nversion = "{version}"\n')
                self.commit()
                self.assertEqual(
                    changed_package_versions(self.root, self.base), ["python/packages/provider/pyproject.toml"]
                )

    def test_root_version_change_triggers(self) -> None:
        manifest = self.root / "python/pyproject.toml"
        manifest.write_text(manifest.read_text().replace('version = "1.0.0"', 'version = "1.1.0"'))
        self.commit()
        self.assertEqual(changed_package_versions(self.root, self.base), ["python/pyproject.toml"])

    def test_multiple_version_changes_are_reported(self) -> None:
        for package in ("core", "provider"):
            self.write(f"python/packages/{package}/pyproject.toml", '[project]\nversion = "1.1.0"\n')
        self.commit()
        self.assertEqual(
            changed_package_versions(self.root, self.base),
            ["python/packages/core/pyproject.toml", "python/packages/provider/pyproject.toml"],
        )

    def test_excluded_standalone_package_does_not_trigger(self) -> None:
        self.write("python/packages/lab/pyproject.toml", '[project]\nversion = "1.0.0a2"\n')
        self.commit()
        self.assertEqual(changed_package_versions(self.root, self.base), [])

    def test_new_workspace_package_triggers(self) -> None:
        self.write("python/packages/new/pyproject.toml", '[project]\nversion = "1.0.0"\n')
        self.commit()
        self.assertEqual(changed_package_versions(self.root, self.base), ["python/packages/new/pyproject.toml"])

    def test_deleted_package_does_not_trigger(self) -> None:
        (self.root / "python/packages/provider/pyproject.toml").unlink()
        self.commit()
        self.assertEqual(changed_package_versions(self.root, self.base), [])

    def test_new_excluded_package_does_not_trigger(self) -> None:
        manifest = self.root / "python/pyproject.toml"
        manifest.write_text(manifest.read_text().replace('["packages/lab"]', '["packages/lab", "packages/standalone"]'))
        self.write("python/packages/standalone/pyproject.toml", '[project]\nversion = "1.0.0"\n')
        self.commit()
        self.assertEqual(changed_package_versions(self.root, self.base), [])

    def test_new_nonmember_package_does_not_trigger(self) -> None:
        manifest = self.root / "python/pyproject.toml"
        manifest.write_text(manifest.read_text().replace('members = ["packages/*"]', 'members = ["packages/core"]'))
        self.write("python/packages/new/pyproject.toml", '[project]\nversion = "1.0.0"\n')
        self.commit()
        self.assertEqual(changed_package_versions(self.root, self.base), [])

    def test_new_package_without_version_fails_instead_of_skipping(self) -> None:
        self.write("python/packages/new/pyproject.toml", '[project]\nname = "new"\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, "project.version"):
            changed_package_versions(self.root, self.base)

    def test_existing_package_added_to_members_triggers(self) -> None:
        manifest = self.root / "python/pyproject.toml"
        config = manifest.read_text()
        manifest.write_text(config.replace('members = ["packages/*"]', 'members = ["packages/core"]'))
        self.commit()
        base = self.git("rev-parse", "HEAD").strip()
        for members in ('["packages/core", "packages/provider"]', '["packages/*"]'):
            with self.subTest(members=members):
                manifest.write_text(config.replace('members = ["packages/*"]', f"members = {members}"))
                self.commit()
                self.assertEqual(changed_package_versions(self.root, base), ["python/packages/provider/pyproject.toml"])

    def test_existing_package_removed_from_exclusions_triggers(self) -> None:
        manifest = self.root / "python/pyproject.toml"
        manifest.write_text(manifest.read_text().replace('["packages/lab"]', '["packages/lab", "packages/pro*"]'))
        self.commit()
        base = self.git("rev-parse", "HEAD").strip()
        manifest.write_text(manifest.read_text().replace('["packages/lab", "packages/pro*"]', '["packages/lab"]'))
        self.commit()
        self.assertEqual(changed_package_versions(self.root, base), ["python/packages/provider/pyproject.toml"])

    def test_removed_workspace_member_does_not_trigger(self) -> None:
        manifest = self.root / "python/pyproject.toml"
        manifest.write_text(manifest.read_text().replace('members = ["packages/*"]', 'members = ["packages/core"]'))
        self.commit()
        self.assertEqual(changed_package_versions(self.root, self.base), [])

    def test_newly_excluded_package_does_not_trigger_even_with_version_change(self) -> None:
        manifest = self.root / "python/pyproject.toml"
        manifest.write_text(manifest.read_text().replace('["packages/lab"]', '["packages/lab", "packages/provider"]'))
        self.write("python/packages/provider/pyproject.toml", '[project]\nversion = "1.1.0"\n')
        self.commit()
        self.assertEqual(changed_package_versions(self.root, self.base), [])

    def test_new_and_bumped_packages_are_both_reported(self) -> None:
        self.write("python/packages/new/pyproject.toml", '[project]\nversion = "1.0.0"\n')
        self.write("python/packages/core/pyproject.toml", '[project]\nversion = "1.1.0"\n')
        self.commit()
        self.assertEqual(
            changed_package_versions(self.root, self.base),
            ["python/packages/core/pyproject.toml", "python/packages/new/pyproject.toml"],
        )

    def test_uses_explicit_base_not_previous_commit_or_moving_branch(self) -> None:
        self.write("python/packages/core/pyproject.toml", '[project]\nversion = "1.1.0"\n')
        self.commit()
        self.git("branch", "moving-base")
        self.write("python/README.md", "An unrelated second PR commit")
        self.commit()
        self.git("branch", "--force", "moving-base", "HEAD")
        self.assertEqual(changed_package_versions(self.root, self.base), ["python/packages/core/pyproject.toml"])
        self.assertEqual(changed_package_versions(self.root, "moving-base"), [])

    def test_uncommitted_versions_are_not_part_of_the_comparison(self) -> None:
        self.write("python/packages/core/pyproject.toml", '[project]\nversion = "1.1.0"\n')
        self.assertEqual(changed_package_versions(self.root, self.base), [])

    def test_merge_commit_compares_against_event_base(self) -> None:
        self.git("checkout", "--quiet", "-b", "release")
        self.write("python/packages/core/pyproject.toml", '[project]\nversion = "1.1.0"\n')
        self.commit()
        self.git("checkout", "--quiet", "-b", "base", self.base)
        self.write("python/packages/provider/pyproject.toml", '[project]\nversion = "1.1.0"\n')
        self.commit()
        event_base = self.git("rev-parse", "HEAD").strip()
        self.git("merge", "--quiet", "--no-ff", "release", "-m", "Synthetic merge")
        self.assertEqual(changed_package_versions(self.root, event_base), ["python/packages/core/pyproject.toml"])

    def test_invalid_or_missing_base_fails_instead_of_skipping(self) -> None:
        with self.assertRaises(ValueError):
            changed_package_versions(self.root, "")
        with self.assertRaisesRegex(RuntimeError, "Git comparison failed"):
            changed_package_versions(self.root, "not-a-ref")

    def test_missing_version_fails_instead_of_skipping(self) -> None:
        self.write("python/packages/core/pyproject.toml", '[project]\nname = "core"\n')
        self.commit()
        with self.assertRaisesRegex(ValueError, "project.version"):
            changed_package_versions(self.root, self.base)

    def test_invalid_toml_fails_instead_of_skipping(self) -> None:
        self.write("python/packages/core/pyproject.toml", '[project\nversion = "1.1.0"\n')
        self.commit()
        with self.assertRaises(ValueError):
            changed_package_versions(self.root, self.base)

    def test_cli_writes_explicit_true_or_false(self) -> None:
        output = self.root / "output"
        for manifests, expected in (([], "false"), (["python/pyproject.toml"], "true")):
            with self.subTest(expected=expected):
                output.write_text("existing=value\n")
                with (
                    patch("sys.argv", ["detect-version-bumps", "--base-ref", self.base, "--github-output", str(output)]),
                    patch(
                        "scripts.dependencies.detect_version_bumps.changed_package_versions", return_value=manifests
                    ),
                ):
                    main()
                self.assertEqual(output.read_text(), f"existing=value\nrequired={expected}\n")


if __name__ == "__main__":
    unittest.main()
