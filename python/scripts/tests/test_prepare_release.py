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
from scripts.prepare_release import SMOKE_IMPORTS, main, selected_versions, validate_manifest


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


def test_generate_and_check_batch_without_duplicate_version_input(workspace: Path, monkeypatch) -> None:
    _bump(workspace, "1.23.0", "1.24.0")
    _bump(workspace / "packages/core", "1.23.0", "1.24.0")
    _bump(workspace / "packages/foundry", "1.15.0", "1.16.0")
    args = ["prepare_release", "--base-ref", "HEAD", "--tag", "python-1.24.0"]
    monkeypatch.setattr(sys, "argv", args)
    main()
    payload = json.loads((workspace / ".github/release.json").read_text())
    assert not (workspace / "release.json").exists()
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
    _bump(workspace / "packages/core", "1.23.0", "1.24.0")
    (workspace / ".github/release.json").write_text(json.dumps(_payload()))
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
    assert not (workspace / ".github/release.json").exists()


def test_ci_requires_manifest_when_versions_change(workspace: Path, monkeypatch) -> None:
    _bump(workspace / "packages/core", "1.23.0", "1.24.0")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--ci", "--base-ref", "HEAD"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_generation_failure_does_not_replace_existing_manifest(workspace: Path, monkeypatch) -> None:
    _project(workspace / "packages/new", "agent-framework-new", "0.1.0")
    _git(workspace, "add", ".")
    (workspace / ".github/release.json").write_text("previous reviewed batch\n")
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--base-ref", "HEAD", "--tag", "python-1.24.0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert (workspace / ".github/release.json").read_text() == "previous reviewed batch\n"


def test_release_event_check_needs_expected_tag_but_not_release_base(workspace: Path, monkeypatch) -> None:
    (workspace / ".github/release.json").write_text(json.dumps(_payload()))
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--tag", "python-1.24.0"])
    main()
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--tag", "python-1.25.0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_root_manifest_is_not_a_fallback(workspace: Path, monkeypatch, capsys) -> None:
    (workspace / "release.json").write_text(json.dumps(_payload()))
    monkeypatch.setattr(sys, "argv", ["prepare_release", "--check", "--tag", "python-1.24.0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert ".github/release.json" in capsys.readouterr().err


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
    (workspace / ".github/release.json").write_text(text)
    _git(workspace, "add", ".github/release.json")
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
