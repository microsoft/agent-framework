# Copyright (c) Microsoft. All rights reserved.

"""Contract and selection tests that do not build or publish distributions."""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import prepare_release
from scripts.dependencies._dependency_bounds_release_impl import _build_release_project_map
from scripts.prepare_release import SMOKE_IMPORTS, main, release_manifest_path, selected_versions, validate_manifest


def _git(path: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=path, check=True, capture_output=True, text=True).stdout.strip()


def _project(path: Path, name: str, version: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "{version}"\nrequires-python = ">=3.10"\n'
    )


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "python"
    _project(root, "agent-framework", "1.23.0")
    with (root / "pyproject.toml").open("a") as file:
        file.write('\n[tool.uv.workspace]\nmembers = ["packages/*"]\nexclude = ["packages/lab"]\n')
    _project(root / "packages/core", "agent-framework-core", "1.23.0")
    _project(root / "packages/foundry", "agent-framework-foundry", "1.15.0")
    _project(root / "packages/lab", "agent-framework-lab", "0.1.0")
    (root / ".github").mkdir()
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "user.name=Release Test", "-c", "user.email=release@example.invalid", "commit", "-qm", "base")
    monkeypatch.setattr(prepare_release, "__file__", str(root / "scripts/prepare_release.py"))
    return root


def _bump(path: Path, old: str, new: str) -> None:
    file = path / "pyproject.toml"
    file.write_text(file.read_text().replace(f'version = "{old}"', f'version = "{new}"'))


def _payload() -> dict:
    return {
        "tag": "python-1.24.0",
        "packages": {"agent-framework": "1.23.0", "agent-framework-foundry": "1.15.0"},
        "smoke_imports": {
            "agent-framework": ["agent_framework:Agent"],
            "agent-framework-foundry": ["agent_framework.foundry:FoundryAgent"],
        },
    }


def test_selection_reuses_metadata_diff_but_only_releases_changed_versions(workspace: Path) -> None:
    _bump(workspace, "1.23.0", "1.24.0")
    _bump(workspace / "packages/core", "1.23.0", "1.24.0")
    with (workspace / "packages/foundry/pyproject.toml").open("a") as file:
        file.write('dependencies = ["agent-framework-core>=1.24.0,<2"]\n')
    _bump(workspace / "packages/lab", "0.1.0", "0.2.0")
    _project(workspace / "packages/new", "agent-framework-new", "0.1.0")
    _git(workspace, "add", ".")
    assert selected_versions(workspace, "HEAD") == {
        "agent-framework": "1.24.0",
        "agent-framework-core": "1.24.0",
        "agent-framework-new": "0.1.0",
    }


def test_selection_rejects_version_regression(workspace: Path) -> None:
    _bump(workspace / "packages/core", "1.23.0", "1.22.0")
    with pytest.raises(ValueError, match="version must increase"):
        selected_versions(workspace, "HEAD")


@pytest.mark.parametrize("with_existing_bump", [False, True])
def test_untracked_metadata_fails_with_staging_instruction(workspace: Path, with_existing_bump: bool) -> None:
    _project(workspace / "packages/new", "agent-framework-new", "0.1.0")
    if with_existing_bump:
        _bump(workspace / "packages/foundry", "1.15.0", "1.16.0")
    with pytest.raises(ValueError, match="Stage new workspace metadata with git add.*packages/new/pyproject.toml"):
        selected_versions(workspace, "HEAD")


def test_untracked_excluded_metadata_does_not_block_selection(workspace: Path) -> None:
    _project(workspace / "packages/lab/nested", "agent-framework-lab-nested", "0.1.0")
    assert selected_versions(workspace, "HEAD") == {}


@pytest.mark.parametrize("version", ["1.15.0", "1.16.0", "1.14.0"])
def test_package_move_compares_distribution_identity(workspace: Path, version: str) -> None:
    (workspace / "packages/foundry").rename(workspace / "packages/moved")
    _bump(workspace / "packages/moved", "1.15.0", version)
    _git(workspace, "add", ".")
    if version == "1.14.0":
        with pytest.raises(ValueError, match="version must increase"):
            selected_versions(workspace, "HEAD")
    else:
        expected = {} if version == "1.15.0" else {"agent-framework-foundry": "1.16.0"}
        assert selected_versions(workspace, "HEAD") == expected


def test_distribution_rename_is_new_even_at_same_version(workspace: Path) -> None:
    _project(workspace / "packages/foundry", "agent-framework-renamed", "1.15.0")
    assert selected_versions(workspace, "HEAD") == {"agent-framework-renamed": "1.15.0"}


def test_excluded_base_distribution_is_new_when_added_to_workspace(workspace: Path) -> None:
    _project(workspace / "packages/foundry", "agent-framework-lab", "0.1.0")
    # Lab is excluded from the base workspace, so this is a genuinely new release identity.
    assert selected_versions(workspace, "HEAD") == {"agent-framework-lab": "0.1.0"}


def test_canonical_identity_change_does_not_create_a_new_distribution(workspace: Path) -> None:
    _project(workspace / "packages/foundry", "agent_framework_foundry", "1.15.0")
    assert selected_versions(workspace, "HEAD") == {}


def test_core_bump_requires_root_version_increase_even_if_pin_is_updated(workspace: Path) -> None:
    _bump(workspace / "packages/core", "1.23.0", "1.24.0")
    root = workspace / "pyproject.toml"
    root.write_text(
        root.read_text().replace(
            'requires-python = ">=3.10"',
            ('requires-python = ">=3.10"\ndependencies = ["agent-framework-core[all]==1.24.0"]'),
        )
    )
    with pytest.raises(ValueError, match="requires a version increase for agent-framework"):
        selected_versions(workspace, "HEAD")


def test_core_and_root_may_bump_together(workspace: Path) -> None:
    _bump(workspace, "1.23.0", "1.24.0")
    _bump(workspace / "packages/core", "1.23.0", "1.24.0")
    assert selected_versions(workspace, "HEAD") == {"agent-framework": "1.24.0", "agent-framework-core": "1.24.0"}


def test_root_may_bump_independently(workspace: Path) -> None:
    _bump(workspace, "1.23.0", "1.24.0")
    assert selected_versions(workspace, "HEAD") == {"agent-framework": "1.24.0"}


def test_generate_and_check_batch_without_duplicate_version_input(workspace: Path, monkeypatch) -> None:
    _bump(workspace, "1.23.0", "1.24.0")
    _bump(workspace / "packages/core", "1.23.0", "1.24.0")
    _bump(workspace / "packages/foundry", "1.15.0", "1.16.0")
    args = ["prepare_release", "--base-ref", "HEAD", "--tag", "python-1.24.0"]
    monkeypatch.setattr(sys, "argv", args)
    main()
    payload = json.loads((workspace / ".github/release-python-1.24.0.json").read_text())
    assert not (workspace / "release.json").exists()
    assert not (workspace / ".github/release.json").exists()
    assert payload["packages"] == {
        "agent-framework": "1.24.0",
        "agent-framework-core": "1.24.0",
        "agent-framework-foundry": "1.16.0",
    }
    assert set(payload["smoke_imports"]) == set(payload["packages"])
    monkeypatch.setattr(sys, "argv", [*args, "--check"])
    main()
    _bump(workspace / "packages/foundry", "1.16.0", "1.17.0")
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_check_rejects_omitted_bumped_distribution(workspace: Path, monkeypatch) -> None:
    _bump(workspace, "1.23.0", "1.24.0")
    _bump(workspace / "packages/core", "1.23.0", "1.24.0")
    (workspace / ".github/release-python-1.24.0.json").write_text(json.dumps(_payload()))
    _git(workspace, "add", ".github/release-python-1.24.0.json")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_ci_skips_unrelated_metadata_edits_without_reading_stale_manifest(workspace: Path, monkeypatch, capsys) -> None:
    with (workspace / "pyproject.toml").open("a") as file:
        file.write("\n[tool.example]\nsetting = true\n")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    main()
    assert "No release batch changes." in capsys.readouterr().out
    assert not list((workspace / ".github").glob("release-*.json"))


def test_ci_requires_manifest_when_versions_change(workspace: Path, monkeypatch) -> None:
    _bump(workspace / "packages/foundry", "1.15.0", "1.16.0")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_ci_allows_new_package_development_without_release_intent(workspace: Path, monkeypatch, capsys) -> None:
    _project(workspace / "packages/new", "agent-framework-new", "0.1.0")
    _git(workspace, "add", ".")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    main()
    assert "New-package development only" in capsys.readouterr().out
    assert not list((workspace / ".github").glob("release-*.json"))


def test_ci_requires_manifest_for_mixed_new_package_and_version_bump(workspace: Path, monkeypatch, capsys) -> None:
    _project(workspace / "packages/new", "agent-framework-new", "0.1.0")
    _bump(workspace / "packages/foundry", "1.15.0", "1.16.0")
    _git(workspace, "add", ".")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "exactly one" in capsys.readouterr().err


def test_ci_with_explicit_tag_requires_manifest_even_for_new_package_only(workspace: Path, monkeypatch, capsys) -> None:
    _project(workspace / "packages/redis", "agent-framework-redis", "1.0.0rc1")
    _git(workspace, "add", ".")
    monkeypatch.setattr(
        sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD", "--tag", "python-1.24.0"]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "exactly one" in capsys.readouterr().err


def test_explicit_new_package_release_is_generated_and_validated(workspace: Path, monkeypatch) -> None:
    _project(workspace / "packages/redis", "agent-framework-redis", "1.0.0rc1")
    _git(workspace, "add", ".")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--base-ref", "HEAD", "--tag", "python-1.24.0"])
    main()
    manifest = workspace / ".github/release-python-1.24.0.json"
    assert json.loads(manifest.read_text())["packages"] == {"agent-framework-redis": "1.0.0rc1"}
    _git(workspace, "add", ".")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    main()


def test_new_package_manifest_is_not_ignored_in_ci(workspace: Path, monkeypatch, capsys) -> None:
    _project(workspace / "packages/redis", "agent-framework-redis", "1.0.0rc1")
    manifest = workspace / ".github/release-python-1.24.0.json"
    manifest.write_text(json.dumps(_payload()))
    _git(workspace, "add", ".")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "must exactly match" in capsys.readouterr().err


@pytest.mark.parametrize("annotated", [False, True])
@pytest.mark.parametrize("mode", ["generate", "check", "ci"])
def test_preparation_rejects_an_existing_tag(workspace: Path, monkeypatch, capsys, annotated: bool, mode: str) -> None:
    _bump(workspace / "packages/foundry", "1.15.0", "1.16.0")
    manifest = workspace / ".github/release-python-1.24.0.json"
    manifest.write_text("{}")
    _git(workspace, "add", ".")
    tag_args = ["tag", "python-1.24.0"]
    if annotated:
        tag_args.extend(["-a", "-m", "existing release"])
    _git(workspace, "-c", "user.name=Release Test", "-c", "user.email=release@example.invalid", *tag_args)
    args = ["prepare_release", "--base-ref", "HEAD"]
    if mode == "ci":
        args.extend(["--check", "--ci"])
    else:
        args.extend(["--tag", "python-1.24.0"])
        if mode == "check":
            args.append("--check")
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "tag python-1.24.0 already exists" in capsys.readouterr().err
    assert manifest.read_text() == "{}"


def test_same_named_branch_does_not_block_a_new_release_tag(workspace: Path, monkeypatch) -> None:
    _git(workspace, "branch", "python-1.24.0")
    _bump(workspace / "packages/foundry", "1.15.0", "1.16.0")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--base-ref", "HEAD", "--tag", "python-1.24.0"])
    main()
    assert (workspace / ".github/release-python-1.24.0.json").exists()


def test_generation_failure_does_not_replace_existing_manifest(workspace: Path, monkeypatch) -> None:
    _project(workspace / "packages/new", "agent-framework-new", "0.1.0")
    _git(workspace, "add", ".")
    (workspace / ".github/release-python-1.24.0.json").write_text("previous reviewed batch\n")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--base-ref", "HEAD", "--tag", "python-1.24.0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert (workspace / ".github/release-python-1.24.0.json").read_text() == "previous reviewed batch\n"


def test_release_event_check_needs_expected_tag_but_not_release_base(workspace: Path, monkeypatch) -> None:
    (workspace / ".github/release-python-1.24.0.json").write_text(json.dumps(_payload()))
    _git(workspace, "tag", "python-1.24.0")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--tag", "python-1.24.0"])
    main()
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--tag", "python-1.25.0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


@pytest.mark.parametrize("old_path", ["release.json", ".github/release.json"])
def test_fixed_manifest_is_not_a_fallback(workspace: Path, monkeypatch, capsys, old_path: str) -> None:
    (workspace / old_path).write_text(json.dumps(_payload()))
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--tag", "python-1.24.0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert str(workspace / ".github/release-python-1.24.0.json") in capsys.readouterr().err


def test_per_tag_path_uses_exact_full_tag() -> None:
    assert release_manifest_path("python-1.24.0") == Path(".github/release-python-1.24.0.json")
    assert release_manifest_path("python-1.0.0b261029") == Path(".github/release-python-1.0.0b261029.json")


@pytest.mark.parametrize("tag", ["../python-1.24.0", "python-1.24.0/../other", "python-1.24.0\n", "python-1.24.0.json"])
def test_path_derivation_rejects_invalid_tags(tag: str) -> None:
    with pytest.raises(ValueError):
        release_manifest_path(tag)


def _commit_archive(workspace: Path) -> Path:
    historical = workspace / ".github/release-python-1.23.0.json"
    historical.write_text(json.dumps({"tag": "python-1.23.0", "packages": {"agent-framework": "1.23.0"}}))
    _git(workspace, "add", ".")
    _git(
        workspace,
        "-c",
        "user.name=Release Test",
        "-c",
        "user.email=release@example.invalid",
        "commit",
        "-qm",
        "archive",
    )
    return historical


def test_generation_and_ci_preserve_history_without_revalidating_old_versions(workspace: Path, monkeypatch) -> None:
    historical = _commit_archive(workspace)
    historical_bytes = historical.read_bytes()
    _bump(workspace, "1.23.0", "1.24.0")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--base-ref", "HEAD", "--tag", "python-1.24.0"])
    main()
    current = workspace / ".github/release-python-1.24.0.json"
    assert json.loads(current.read_text())["packages"] == {"agent-framework": "1.24.0"}
    _git(workspace, "add", ".")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    main()
    assert historical.read_bytes() == historical_bytes


@pytest.mark.parametrize("action", ["modify", "delete", "regenerate"])
def test_historical_manifest_cannot_be_changed_or_removed(workspace: Path, monkeypatch, capsys, action: str) -> None:
    historical = _commit_archive(workspace)
    if action == "regenerate":
        args = ["prepare_release", "--base-ref", "HEAD", "--tag", "python-1.23.0"]
    else:
        if action == "modify":
            historical.write_text("{}")
        else:
            historical.unlink()
        args = ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "Historical release manifests" in capsys.readouterr().err


def test_ci_rejects_multiple_new_batch_files(workspace: Path, monkeypatch, capsys) -> None:
    for tag in ("python-1.24.0", "python-1.25.0"):
        (workspace / release_manifest_path(tag)).write_text(json.dumps(_payload()))
    _git(workspace, "add", ".")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "exactly one" in capsys.readouterr().err


def test_ci_rejects_renaming_a_historical_manifest(workspace: Path, monkeypatch, capsys) -> None:
    historical = _commit_archive(workspace)
    historical.rename(workspace / ".github/release-python-1.24.0.json")
    _git(workspace, "add", ".")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "exactly one" in capsys.readouterr().err


def test_ci_rejects_filename_content_tag_mismatch(workspace: Path, monkeypatch, capsys) -> None:
    (workspace / ".github/release-python-1.25.0.json").write_text(json.dumps(_payload()))
    _git(workspace, "add", ".")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "expected tag python-1.25.0" in capsys.readouterr().err


def test_explicit_tag_never_falls_back_to_another_historical_manifest(workspace: Path, monkeypatch, capsys) -> None:
    _commit_archive(workspace)
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--tag", "python-1.24.0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert str(workspace / ".github/release-python-1.24.0.json") in capsys.readouterr().err


@pytest.mark.parametrize("tag", ["python-1.24.0", "python-1.0.0b261029", "python-1.0.0rc2", "python-1.0.0.post1"])
def test_overall_tags_allow_independent_package_versions(workspace: Path, tag: str) -> None:
    payload = _payload()
    payload["tag"] = tag
    validate_manifest(payload, _build_release_project_map(workspace), expected_tag=tag)


@pytest.mark.parametrize("tag", ["python-foundry-1.16.0", "python-", "v1.24.0", "python-1.0.0nonsense", "python-1.2"])
def test_rejects_invalid_and_per_package_tags(workspace: Path, tag: str) -> None:
    with pytest.raises(ValueError):
        validate_manifest(_payload(), _build_release_project_map(workspace), expected_tag=tag)


def test_expected_tag_prevents_reuse_of_stale_manifest(workspace: Path) -> None:
    with pytest.raises(ValueError, match="expected tag"):
        validate_manifest(_payload(), _build_release_project_map(workspace), expected_tag="python-1.25.0")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("packages", {}),
        ("packages", []),
        ("packages", {"agent_framework": "1.23.0"}),
        ("packages", {"agent-framework-lab": "0.1.0"}),
        ("packages", {"agent-framework": "1.24.0"}),
        ("packages", {"agent-framework": 123}),
        ("smoke_imports", []),
        ("smoke_imports", {"agent-framework-core": ["agent_framework:Message"]}),
        ("smoke_imports", {"agent-framework": []}),
        ("smoke_imports", {"agent-framework": ["agent_framework_meta:Agent"]}),
        ("smoke_imports", {"agent-framework": ["agent_framework._agents:Agent"]}),
    ],
)
def test_rejects_invalid_contract(workspace: Path, field: str, value: object) -> None:
    payload = _payload()
    payload[field] = value
    with pytest.raises(ValueError):
        validate_manifest(payload, _build_release_project_map(workspace), expected_tag="python-1.24.0")


def test_unknown_distribution_requires_reviewed_imports(workspace: Path) -> None:
    _project(workspace / "packages/new", "agent-framework-new", "0.1.0")
    payload = {"tag": "python-1.24.0", "packages": {"agent-framework-new": "0.1.0"}}
    with pytest.raises(ValueError, match="add reviewed public smoke imports"):
        validate_manifest(payload, _build_release_project_map(workspace), expected_tag="python-1.24.0")


def test_non_default_distribution_requires_smoke_imports(workspace: Path) -> None:
    _project(workspace / "packages/redis", "agent-framework-redis", "1.0.0rc1")
    payload = {"tag": "python-1.24.0", "packages": {"agent-framework-redis": "1.0.0rc1"}}
    with pytest.raises(ValueError, match="non-empty public module:export"):
        validate_manifest(payload, _build_release_project_map(workspace), expected_tag="python-1.24.0")
    payload["smoke_imports"] = {"agent-framework-redis": ["agent_framework.redis:RedisStore"]}
    validate_manifest(payload, _build_release_project_map(workspace), expected_tag="python-1.24.0")


def test_smoke_imports_are_additive_and_default_mapping_is_optional(workspace: Path) -> None:
    payload = _payload()
    payload.pop("smoke_imports")
    validate_manifest(payload, _build_release_project_map(workspace), expected_tag="python-1.24.0")
    payload["smoke_imports"] = {"agent-framework": ["agent_framework:Agent", "agent_framework:Message"]}
    validate_manifest(payload, _build_release_project_map(workspace), expected_tag="python-1.24.0")


@pytest.mark.parametrize("text", ['{"tag":"python-1.24.0","tag":"python-1.25.0"}', '["invalid"]', "{"])
def test_cli_rejects_malformed_manifest(workspace: Path, monkeypatch, text: str) -> None:
    (workspace / ".github/release-python-1.24.0.json").write_text(text)
    _git(workspace, "add", ".github/release-python-1.24.0.json")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_inventory_covers_every_workspace_distribution_with_a_public_export() -> None:
    root = Path(__file__).resolve().parents[2]
    projects = _build_release_project_map(root)
    assert set(SMOKE_IMPORTS) == set(projects)
    for distribution, imports in SMOKE_IMPORTS.items():
        for value in imports:
            module, symbol = value.split(":")
            relative = Path(*module.split(".")) / "__init__.py"
            candidates = list(root.glob(f"packages/*/{relative}"))
            assert len(candidates) == 1, (distribution, module)
            tree = ast.parse(candidates[0].read_text())
            public_names: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    if any(isinstance(target, ast.Name) and target.id in {"__all__", "_IMPORTS"} for target in targets):
                        public_names.update(
                            child.value
                            for child in ast.walk(node.value)
                            if isinstance(child, ast.Constant) and isinstance(child.value, str)
                        )
            assert symbol in public_names, (distribution, module, symbol)
