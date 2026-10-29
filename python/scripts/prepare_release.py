# Copyright (c) Microsoft. All rights reserved.

"""Generate or check the reviewed batch consumed by the Azure DevOps publisher."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name
from packaging.version import Version

from scripts.dependencies._dependency_bounds_release_impl import (
    ReleaseProject,
    _build_release_project_map,
    _selected_release_projects,
)

RELEASE_MANIFEST_GLOB = ".github/release-*.json"

# Prefer the public namespace bridges; use documented package entry points where
# no bridge exists. Importing the build module (e.g. agent_framework_meta) is not a smoke test.
SMOKE_IMPORTS: dict[str, tuple[str, ...]] = {
    "agent-framework": ("agent_framework:Agent",),
    "agent-framework-core": ("agent_framework:Message",),
    "agent-framework-a2a": ("agent_framework.a2a:A2AAgent",),
    "agent-framework-ag-ui": ("agent_framework.ag_ui:AgentFrameworkAgent",),
    "agent-framework-anthropic": ("agent_framework.anthropic:AnthropicClient",),
    "agent-framework-azure-ai-search": ("agent_framework.azure:AzureAISearchStore",),
    "agent-framework-azure-contentunderstanding": ("agent_framework.foundry:ContentUnderstandingContextProvider",),
    "agent-framework-azure-cosmos": ("agent_framework.azure:CosmosStore",),
    "agent-framework-azure-cosmos-memory": ("agent_framework_azure_cosmos_memory:CosmosMemoryContextProvider",),
    "agent-framework-azure-documentdb": ("agent_framework_azure_documentdb:AzureDocumentDBStore",),
    "agent-framework-bedrock": ("agent_framework.amazon:BedrockChatClient",),
    "agent-framework-chatkit": ("agent_framework.chatkit:stream_agent_response",),
    "agent-framework-claude": ("agent_framework.anthropic:ClaudeAgent",),
    "agent-framework-copilotstudio": ("agent_framework.microsoft:CopilotStudioAgent",),
    "agent-framework-declarative": ("agent_framework.declarative:AgentFactory",),
    "agent-framework-devui": ("agent_framework.devui:serve",),
    "agent-framework-duckdb": ("agent_framework_duckdb:DuckDBStore",),
    "agent-framework-foundry": ("agent_framework.foundry:FoundryAgent",),
    "agent-framework-foundry-hosting": ("agent_framework.foundry:FoundryAgentSessionStore",),
    "agent-framework-foundry-local": ("agent_framework.foundry:FoundryLocalClient",),
    "agent-framework-gemini": ("agent_framework.gemini:GeminiEmbeddingClient",),
    "agent-framework-github-copilot": ("agent_framework.github:GitHubCopilotAgent",),
    "agent-framework-hosting": ("agent_framework_hosting:AgentState",),
    "agent-framework-hosting-a2a": ("agent_framework_hosting_a2a:AgentA2AAdapter",),
    "agent-framework-hosting-mcp": ("agent_framework_hosting_mcp:AgentMCPTool",),
    "agent-framework-hosting-responses": ("agent_framework_hosting_responses:responses_from_run",),
    "agent-framework-hosting-telegram": ("agent_framework_hosting_telegram:telegram_to_run",),
    "agent-framework-hyperlight": ("agent_framework.hyperlight:HyperlightCodeActProvider",),
    "agent-framework-mem0": ("agent_framework.mem0:Mem0ContextProvider",),
    "agent-framework-mistral": ("agent_framework.mistral:MistralChatClient",),
    "agent-framework-mongodb": ("agent_framework_mongodb:MongoDBStore",),
    "agent-framework-monty": ("agent_framework.monty:MontyCodeActProvider",),
    "agent-framework-nvidia": ("agent_framework_nvidia:NvidiaEmbeddingClient",),
    "agent-framework-ollama": ("agent_framework.ollama:OllamaChatClient",),
    "agent-framework-openai": ("agent_framework.openai:OpenAIChatClient",),
    "agent-framework-oracle": ("agent_framework_oracle:OracleStore",),
    "agent-framework-orchestrations": ("agent_framework.orchestrations:SequentialBuilder",),
    "agent-framework-postgres": ("agent_framework_postgres:PostgresStore",),
    "agent-framework-purview": ("agent_framework.microsoft:PurviewPolicyMiddleware",),
    "agent-framework-qdrant": ("agent_framework_qdrant:QdrantStore",),
    "agent-framework-redis": ("agent_framework.redis:RedisStore",),
    "agent-framework-sql-server": ("agent_framework_sql_server:SqlServerStore",),
    "agent-framework-tools": ("agent_framework.tools:LocalShellTool",),
    "agent-framework-typesafe": ("agent_framework_typesafe:TypeSafeChatClient",),
}


def _git(workspace_root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=workspace_root, capture_output=True, text=True, check=True).stdout


def _base_release_versions(workspace_root: Path, base_commit: str) -> dict[str, str]:
    """Discover the base workspace by the same membership rules as the current tree."""
    paths = _git(
        workspace_root, "ls-tree", "-r", "--name-only", "-z", base_commit, "--", "pyproject.toml", "packages/"
    ).split("\0")
    with tempfile.TemporaryDirectory(prefix="release-metadata-") as directory:
        snapshot = Path(directory)
        for value in paths:
            path = Path(value)
            if path.name != "pyproject.toml":
                continue
            destination = snapshot / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(_git(workspace_root, "show", f"{base_commit}:./{path.as_posix()}"))
        return {name: project.version for name, project in _build_release_project_map(snapshot).items()}


def selected_versions(workspace_root: Path, base_ref: str) -> dict[str, str]:
    """Reuse release-probe selection, excluding dependency-only metadata edits."""
    base_commit = _git(workspace_root, "rev-parse", "--verify", "--end-of-options", f"{base_ref}^{{commit}}").strip()
    projects = _build_release_project_map(workspace_root)
    untracked = set(_git(workspace_root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"))
    untracked_metadata = sorted(
        (project.project_path / "pyproject.toml").as_posix()
        for project in projects.values()
        if (project.project_path / "pyproject.toml").as_posix() in untracked
    )
    if untracked_metadata:
        raise ValueError(
            "Stage new workspace metadata with git add before preparing a release: " + ", ".join(untracked_metadata)
        )
    base_versions = _base_release_versions(workspace_root, base_commit)
    selected = _selected_release_projects(
        workspace_root=workspace_root, projects=projects, base_ref=base_commit, package_filter=None
    )
    versions: dict[str, str] = {}
    for project in selected:
        name = canonicalize_name(project.package_name)
        if name in base_versions:
            previous_version = Version(base_versions[name])
            if previous_version == Version(project.version):
                continue
            if Version(project.version) < previous_version:
                raise ValueError(f"{project.package_name}: version must increase from {previous_version}")
        versions[project.package_name] = project.version
    if "agent-framework-core" in versions and "agent-framework" not in versions:
        raise ValueError("Releasing agent-framework-core requires a version increase for agent-framework too")
    return dict(sorted(versions.items()))


def _validate_tag(tag: object) -> None:
    if not isinstance(tag, str) or not re.fullmatch(r"python-[0-9]+\.[0-9]+\.[0-9]+[a-zA-Z0-9.]*", tag):
        raise ValueError("Expected one overall python-<PEP440-version> tag, not a per-package tag")
    Version(tag.removeprefix("python-"))


def release_manifest_path(tag: str) -> Path:
    """Derive the request path from the exact expected overall tag."""
    _validate_tag(tag)
    return Path(".github") / f"release-{tag}.json"


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate manifest key: {key}")
        result[key] = value
    return result


def validate_manifest(
    payload: object,
    projects: dict[str, ReleaseProject],
    *,
    expected_tag: str,
) -> None:
    """Check the contract without contacting PyPI or executing package imports."""
    _validate_tag(expected_tag)
    if not isinstance(payload, dict) or set(payload) - {"tag", "packages", "smoke_imports"}:
        raise ValueError("Manifest must be an object containing tag, packages, and optional smoke_imports")
    if payload.get("tag") != expected_tag:
        raise ValueError(f"Manifest tag does not match expected tag {expected_tag}")
    packages = payload.get("packages")
    if not isinstance(packages, dict) or not packages:
        raise ValueError("Manifest packages must be a non-empty object")
    smoke_imports = payload.get("smoke_imports", {})
    if not isinstance(smoke_imports, dict) or set(smoke_imports) - set(packages):
        raise ValueError("smoke_imports must be an object keyed only by selected distributions")
    for name, version in packages.items():
        if not isinstance(name, str) or canonicalize_name(name) != name or name not in projects:
            raise ValueError(f"Unknown or non-canonical distribution: {name}")
        if not isinstance(version, str) or version != projects[name].version:
            raise ValueError(f"{name}: manifest version must equal project.version {projects[name].version}")
        Version(version)
        if name not in SMOKE_IMPORTS:
            raise ValueError(f"{name}: add reviewed public smoke imports before releasing this package")
        # Older consumers have defaults for these three distributions only.
        imports = smoke_imports.get(
            name,
            list(SMOKE_IMPORTS[name])
            if name in {"agent-framework", "agent-framework-core", "agent-framework-foundry"}
            else None,
        )
        if (
            not isinstance(imports, list)
            or not imports
            or any(
                not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z]\w*(?:\.[a-zA-Z]\w*)*:[a-zA-Z]\w*", value)
                for value in imports
            )
        ):
            raise ValueError(f"{name}: expected non-empty public module:export smoke imports")
        if not set(SMOKE_IMPORTS[name]).issubset(imports):
            raise ValueError(
                f"{name}: smoke imports must include the reviewed public entry points {SMOKE_IMPORTS[name]}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", help="Same main ref used by validate-python-release")
    parser.add_argument(
        "--tag", help="Expected overall python-* tag (required to generate or validate a release event)"
    )
    parser.add_argument(
        "--check", action="store_true", help="Validate instead of writing .github/release-<fulltag>.json"
    )
    parser.add_argument(
        "--ci", action="store_true", help="Check changed batches; skip PRs with no version/manifest change"
    )
    args = parser.parse_args()
    workspace_root = Path(__file__).resolve().parents[1]
    if (not args.check or args.ci) and not args.base_ref:
        parser.error("--base-ref is required for generation and --ci")
    if args.ci and not args.check:
        parser.error("--ci requires --check")
    if not args.ci and not args.tag:
        parser.error("--tag is required outside PR CI")
    try:
        base_commit = (
            _git(workspace_root, "rev-parse", "--verify", "--end-of-options", f"{args.base_ref}^{{commit}}").strip()
            if args.base_ref
            else None
        )
        versions = selected_versions(workspace_root, base_commit) if base_commit else None
        expected_tag = args.tag
        if args.ci:
            changed_paths = [
                Path(value)
                for value in _git(
                    workspace_root,
                    "diff",
                    "--relative",
                    "--no-renames",
                    "--name-only",
                    "-z",
                    base_commit,
                    "--",
                    RELEASE_MANIFEST_GLOB,
                ).split("\0")
                if value
            ]
            if not versions and not changed_paths:
                print("No release batch changes.")
                return
            if (
                not changed_paths
                and not args.tag
                and versions
                and not (set(versions) & _base_release_versions(workspace_root, base_commit).keys())
            ):
                print("New-package development only; no release manifest required.")
                return
            if len(changed_paths) != 1:
                raise ValueError("A release PR must add exactly one .github/release-<fulltag>.json batch")
            expected_tag = expected_tag or changed_paths[0].stem.removeprefix("release-")
            if changed_paths[0] != release_manifest_path(expected_tag):
                raise ValueError("Changed manifest filename does not match the expected release tag")
        relative_manifest = release_manifest_path(expected_tag)
        manifest_path = workspace_root / relative_manifest
        if (
            base_commit
            and _git(workspace_root, "ls-tree", "--name-only", base_commit, "--", relative_manifest.as_posix()).strip()
        ):
            raise ValueError("Historical release manifests must not be changed or removed; use a new tag")
        if (
            base_commit
            and f"refs/tags/{expected_tag}"
            in _git(workspace_root, "for-each-ref", "--format=%(refname)", f"refs/tags/{expected_tag}").splitlines()
        ):
            raise ValueError(f"Release tag {expected_tag} already exists; choose a new overall release tag")
        if args.check:
            payload = json.loads(manifest_path.read_text(), object_pairs_hook=_reject_duplicate_keys)
        else:
            payload = {
                "tag": args.tag,
                "packages": versions,
                "smoke_imports": {name: list(SMOKE_IMPORTS.get(name, ())) for name in versions or {}},
            }
        validate_manifest(payload, _build_release_project_map(workspace_root), expected_tag=expected_tag)
        if versions is not None and payload["packages"] != versions:
            raise ValueError("Manifest packages must exactly match version changes from --base-ref; regenerate it")
        if not args.check:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(payload, indent=2) + "\n")
        print(
            f"{'Validated' if args.check else 'Generated'} {relative_manifest.as_posix()} for {expected_tag}: "
            f"{len(payload['packages'])} packages"
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Release manifest error: {exc}\n")


if __name__ == "__main__":
    main()
