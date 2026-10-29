# Copyright (c) Microsoft. All rights reserved.

"""Generate or check the reviewed batch consumed by the Azure DevOps publisher."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from packaging.utils import canonicalize_name
from packaging.version import Version

from scripts._toml import tomllib
from scripts.dependencies._dependency_bounds_release_impl import (
    ReleaseProject,
    _build_release_project_map,
    _selected_release_projects,
)

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


def selected_versions(workspace_root: Path, base_ref: str) -> dict[str, str]:
    """Reuse release-probe selection, excluding dependency-only metadata edits."""
    base_commit = _git(workspace_root, "rev-parse", "--verify", "--end-of-options", f"{base_ref}^{{commit}}").strip()
    projects = _build_release_project_map(workspace_root)
    selected = _selected_release_projects(
        workspace_root=workspace_root, projects=projects, base_ref=base_commit, package_filter=None
    )
    versions: dict[str, str] = {}
    for project in selected:
        path = project.project_path / "pyproject.toml"
        if _git(workspace_root, "ls-tree", "--name-only", base_commit, "--", path.as_posix()).strip():
            previous = tomllib.loads(_git(workspace_root, "show", f"{base_commit}:./{path.as_posix()}"))["project"]
            if Version(previous["version"]) == Version(project.version):
                continue
            if Version(project.version) <= Version(previous["version"]):
                raise ValueError(f"{project.package_name}: version must increase from {previous['version']}")
        versions[project.package_name] = project.version
    return dict(sorted(versions.items()))


def _validate_tag(tag: object) -> None:
    if not isinstance(tag, str) or not re.fullmatch(r"python-[0-9]+\.[0-9]+\.[0-9]+[a-zA-Z0-9.]*", tag):
        raise ValueError("Expected one overall python-<PEP440-version> tag, not a per-package tag")
    Version(tag.removeprefix("python-"))


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
    parser.add_argument("--check", action="store_true", help="Validate instead of writing release.json")
    parser.add_argument(
        "--ci", action="store_true", help="Check changed batches; skip PRs with no version/manifest change"
    )
    args = parser.parse_args()
    workspace_root = Path(__file__).resolve().parents[1]
    manifest_path = workspace_root / "release.json"
    if (not args.check or args.ci) and not args.base_ref:
        parser.error("--base-ref is required for generation and --ci")
    if args.ci and not args.check:
        parser.error("--ci requires --check")
    if not args.ci and not args.tag:
        parser.error("--tag is required outside PR CI")
    try:
        versions = selected_versions(workspace_root, args.base_ref) if args.base_ref else None
        if (
            args.ci
            and not versions
            and not _git(workspace_root, "diff", "--name-only", args.base_ref, "--", "release.json").strip()
        ):
            print("No release batch changes.")
            return
        if args.check:
            payload = json.loads(manifest_path.read_text(), object_pairs_hook=_reject_duplicate_keys)
        else:
            payload = {
                "tag": args.tag,
                "packages": versions,
                "smoke_imports": {name: list(SMOKE_IMPORTS.get(name, ())) for name in versions or {}},
            }
        expected_tag = args.tag or (payload.get("tag") if isinstance(payload, dict) else None)
        validate_manifest(payload, _build_release_project_map(workspace_root), expected_tag=expected_tag)
        if versions is not None and payload["packages"] != versions:
            raise ValueError("Manifest packages must exactly match version changes from --base-ref; regenerate it")
        if not args.check:
            manifest_path.write_text(json.dumps(payload, indent=2) + "\n")
        print(
            f"{'Validated' if args.check else 'Generated'} release.json for {expected_tag}: "
            f"{len(payload['packages'])} packages"
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Release manifest error: {exc}\n")


if __name__ == "__main__":
    main()
