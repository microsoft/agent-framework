# Copyright (c) Microsoft. All rights reserved.

"""File-based Agent Skills provider for the agent framework.

This module implements the progressive disclosure pattern from the
`Agent Skills specification <https://agentskills.io/>`_:

1. **Advertise** — skill names and descriptions are injected into the system prompt.
2. **Load** — the full SKILL.md body is returned via the ``load_skill`` tool.
3. **Read resources** — supplementary files are read from disk on demand via
   the ``read_skill_resource`` tool.

Skills are discovered by searching configured directories for ``SKILL.md`` files.
Referenced resources are validated at initialization; invalid skills are excluded
and logged.

**Security:** this provider only reads static content. Skill metadata is XML-escaped
before prompt embedding, and resource reads are guarded against path traversal and
symlink escape. Only use skills from trusted sources.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from html import escape as xml_escape
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, ClassVar, Final

from ._sessions import BaseContextProvider
from ._tools import FunctionTool

if TYPE_CHECKING:
    from ._agents import SupportsAgentRun
    from ._sessions import AgentSession, SessionContext

logger = logging.getLogger(__name__)

# region Constants

SKILL_FILE_NAME: Final[str] = "SKILL.md"
MAX_SEARCH_DEPTH: Final[int] = 2
MAX_NAME_LENGTH: Final[int] = 64
MAX_DESCRIPTION_LENGTH: Final[int] = 1024

# endregion

# region Compiled regex patterns (ported from .NET FileAgentSkillLoader)

# Matches YAML frontmatter delimited by "---" lines.
# The \uFEFF? prefix allows an optional UTF-8 BOM.
_FRONTMATTER_RE = re.compile(
    r"\A\uFEFF?---\s*$(.+?)^---\s*$",
    re.MULTILINE | re.DOTALL,
)

# Matches resource file references in skill markdown. Group 1 = relative file path.
# Supports two forms:
#   1. Markdown links: [text](path/file.ext)
#   2. Backtick-quoted paths: `path/file.ext`
# Supports optional ./ or ../ prefixes; excludes URLs (no ":" in the path character class).
_RESOURCE_LINK_RE = re.compile(
    r"(?:\[.*?\]\(|`)(\.?\.?/?[\w][\w\-./]*\.\w+)(?:\)|`)",
)

# Matches YAML "key: value" lines. Group 1 = key, Group 2 = quoted value,
# Group 3 = unquoted value.
_YAML_KV_RE = re.compile(
    r"^\s*(\w+)\s*:\s*(?:[\"'](.+?)[\"']|(.+?))\s*$",
    re.MULTILINE,
)

# Validates skill names: lowercase letters, numbers, hyphens only;
# must not start or end with a hyphen.
_VALID_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$")

_DEFAULT_SKILLS_INSTRUCTION_PROMPT = """\
You have access to skills containing domain-specific knowledge and capabilities.
Each skill provides specialized instructions, reference documents, and assets for specific tasks.

<available_skills>
{0}
</available_skills>

When a task aligns with a skill's domain:
1. Use `load_skill` to retrieve the skill's instructions
2. Follow the provided guidance
3. Use `read_skill_resource` to read any references or other files mentioned by the skill,
   always using the full path as written (e.g. `references/FAQ.md`, not just `FAQ.md`)

Only load what is needed, when it is needed."""

# endregion

# region Private data classes


@dataclass
class _SkillFrontmatter:
    """Parsed YAML frontmatter from a SKILL.md file."""

    name: str
    description: str


@dataclass
class _FileAgentSkill:
    """Represents a loaded Agent Skill discovered from a filesystem directory."""

    frontmatter: _SkillFrontmatter
    body: str
    source_path: str
    resource_names: list[str] = field(default_factory=list)

# endregion

# region Private module-level functions (skill discovery, parsing, security)


def _normalize_resource_path(path: str) -> str:
    """Normalize a relative resource path.

    Replaces backslashes with forward slashes and removes leading ``./`` prefixes
    so that ``./refs/doc.md`` and ``refs/doc.md`` are treated as the same resource.
    """
    return PurePosixPath(path.replace("\\", "/")).as_posix()


def _extract_resource_paths(content: str) -> list[str]:
    """Extract deduplicated resource paths from markdown link syntax."""
    seen: set[str] = set()
    paths: list[str] = []
    for match in _RESOURCE_LINK_RE.finditer(content):
        normalized = _normalize_resource_path(match.group(1))
        lower = normalized.lower()
        if lower not in seen:
            seen.add(lower)
            paths.append(normalized)
    return paths


def _is_path_within_directory(full_path: str, directory_path: str) -> bool:
    """Check that *full_path* is under *directory_path*.

    Uses :meth:`pathlib.Path.is_relative_to` for cross-platform comparison,
    which handles case sensitivity correctly per platform.
    """
    try:
        return Path(full_path).is_relative_to(directory_path)
    except (ValueError, OSError):
        return False


def _has_symlink_in_path(full_path: str, directory_path: str) -> bool:
    """Check whether any segment in *full_path* below *directory_path* is a symlink.

    Precondition: *full_path* must start with *directory_path*.  Callers are
    expected to verify containment via :func:`_is_path_within_directory` before
    invoking this function.
    """
    dir_path = Path(directory_path)
    try:
        relative = Path(full_path).relative_to(dir_path)
    except ValueError as exc:
        raise ValueError(
            f"full_path {full_path!r} does not start with directory_path {directory_path!r}"
        ) from exc

    current = dir_path
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _try_parse_skill_document(
    content: str,
    skill_file_path: str,
) -> tuple[_SkillFrontmatter, str] | None:
    """Parse a SKILL.md file into frontmatter and body.

    Returns:
        A ``(frontmatter, body)`` tuple on success, or ``None`` if parsing fails.
    """
    match = _FRONTMATTER_RE.search(content)
    if not match:
        logger.error("SKILL.md at '%s' does not contain valid YAML frontmatter delimited by '---'", skill_file_path)
        return None

    yaml_content = match.group(1).strip()
    name: str | None = None
    description: str | None = None

    for kv_match in _YAML_KV_RE.finditer(yaml_content):
        key = kv_match.group(1)
        value = kv_match.group(2) if kv_match.group(2) is not None else kv_match.group(3)

        if key.lower() == "name":
            name = value
        elif key.lower() == "description":
            description = value

    if not name or not name.strip():
        logger.error("SKILL.md at '%s' is missing a 'name' field in frontmatter", skill_file_path)
        return None

    if len(name) > MAX_NAME_LENGTH or not _VALID_NAME_RE.match(name):
        logger.error(
            "SKILL.md at '%s' has an invalid 'name' value: Must be %d characters or fewer, "
            "using only lowercase letters, numbers, and hyphens, and must not start or end with a hyphen.",
            skill_file_path,
            MAX_NAME_LENGTH,
        )
        return None

    if not description or not description.strip():
        logger.error("SKILL.md at '%s' is missing a 'description' field in frontmatter", skill_file_path)
        return None

    if len(description) > MAX_DESCRIPTION_LENGTH:
        logger.error(
            "SKILL.md at '%s' has an invalid 'description' value: Must be %d characters or fewer.",
            skill_file_path,
            MAX_DESCRIPTION_LENGTH,
        )
        return None

    body = content[match.end() :].lstrip()
    return _SkillFrontmatter(name, description), body


def _validate_resources(
    skill_dir_path: str,
    resource_names: list[str],
    skill_name: str,
) -> bool:
    """Validate that all resource paths exist and are safe."""
    skill_dir = Path(skill_dir_path).absolute()

    for resource_name in resource_names:
        resource_path = Path(os.path.normpath(skill_dir / resource_name))

        if not _is_path_within_directory(str(resource_path), str(skill_dir)):
            logger.warning(
                "Excluding skill '%s': resource '%s' references a path outside the skill directory",
                skill_name,
                resource_name,
            )
            return False

        if not resource_path.is_file():
            logger.warning(
                "Excluding skill '%s': referenced resource '%s' does not exist",
                skill_name,
                resource_name,
            )
            return False

        if _has_symlink_in_path(str(resource_path), str(skill_dir)):
            logger.warning(
                "Excluding skill '%s': resource '%s' is a symlink that resolves outside the skill directory",
                skill_name,
                resource_name,
            )
            return False

    return True


def _parse_skill_file(skill_dir_path: str) -> _FileAgentSkill | None:
    """Parse a SKILL.md file from the given directory."""
    skill_file = Path(skill_dir_path) / SKILL_FILE_NAME

    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError:
        logger.error("Failed to read SKILL.md at '%s'", skill_file)
        return None

    result = _try_parse_skill_document(content, str(skill_file))
    if result is None:
        return None

    frontmatter, body = result
    resource_names = _extract_resource_paths(body)

    if not _validate_resources(skill_dir_path, resource_names, frontmatter.name):
        return None

    return _FileAgentSkill(
        frontmatter=frontmatter,
        body=body,
        source_path=skill_dir_path,
        resource_names=resource_names,
    )


def _search_directories_for_skills(
    directory: str,
    results: list[str],
    current_depth: int,
) -> None:
    """Recursively search for SKILL.md files up to *MAX_SEARCH_DEPTH*."""
    dir_path = Path(directory)
    if (dir_path / SKILL_FILE_NAME).is_file():
        results.append(str(dir_path.absolute()))

    if current_depth >= MAX_SEARCH_DEPTH:
        return

    try:
        entries = list(dir_path.iterdir())
    except OSError:
        return

    for entry in entries:
        if entry.is_dir():
            _search_directories_for_skills(str(entry), results, current_depth + 1)


def _discover_skill_directories(skill_paths: Sequence[str]) -> list[str]:
    """Discover all directories containing SKILL.md files."""
    discovered: list[str] = []
    for root_dir in skill_paths:
        if not root_dir or not root_dir.strip() or not Path(root_dir).is_dir():
            continue
        _search_directories_for_skills(root_dir, discovered, current_depth=0)
    return discovered


def _discover_and_load_skills(skill_paths: Sequence[str]) -> dict[str, _FileAgentSkill]:
    """Discover and load all valid skills from the given paths."""
    skills: dict[str, _FileAgentSkill] = {}

    discovered = _discover_skill_directories(skill_paths)
    logger.info("Discovered %d potential skills", len(discovered))

    for skill_path in discovered:
        skill = _parse_skill_file(skill_path)
        if skill is None:
            continue

        if skill.frontmatter.name in skills:
            existing = skills[skill.frontmatter.name]
            logger.warning(
                "Duplicate skill name '%s': skill from '%s' skipped in favor of existing skill from '%s'",
                skill.frontmatter.name,
                skill_path,
                existing.source_path,
            )
            continue

        skills[skill.frontmatter.name] = skill
        logger.info("Loaded skill: %s", skill.frontmatter.name)

    logger.info("Successfully loaded %d skills", len(skills))
    return skills


def _read_skill_resource(skill: _FileAgentSkill, resource_name: str) -> str:
    """Read a resource file from disk with path traversal and symlink guards.

    Args:
        skill: The skill that owns the resource.
        resource_name: Relative path of the resource within the skill directory.

    Returns:
        The UTF-8 text content of the resource file.

    Raises:
        ValueError: The resource is not registered, resolves outside the skill
            directory, or does not exist.
    """
    resource_name = _normalize_resource_path(resource_name)

    # Find the registered resource name with the original casing so the
    # file path is correct on case-sensitive filesystems.
    registered_name: str | None = None
    for r in skill.resource_names:
        if r.lower() == resource_name.lower():
            registered_name = r
            break

    if registered_name is None:
        raise ValueError(f"Resource '{resource_name}' not found in skill '{skill.frontmatter.name}'.")

    full_path = os.path.normpath(Path(skill.source_path) / registered_name)
    source_dir = str(Path(skill.source_path).absolute())

    if not _is_path_within_directory(full_path, source_dir):
        raise ValueError(f"Resource file '{resource_name}' references a path outside the skill directory.")

    if not Path(full_path).is_file():
        raise ValueError(f"Resource file '{resource_name}' not found in skill '{skill.frontmatter.name}'.")

    if _has_symlink_in_path(full_path, source_dir):
        raise ValueError(f"Resource file '{resource_name}' is a symlink that resolves outside the skill directory.")

    logger.info("Reading resource '%s' from skill '%s'", resource_name, skill.frontmatter.name)
    return Path(full_path).read_text(encoding="utf-8")


def _build_skills_instruction_prompt(
    prompt_template: str | None,
    skills: dict[str, _FileAgentSkill],
) -> str | None:
    """Build the system prompt advertising available skills."""
    template = _DEFAULT_SKILLS_INSTRUCTION_PROMPT

    if prompt_template is not None:
        # Validate that the custom template contains a valid {0} placeholder
        try:
            prompt_template.format("")
            template = prompt_template
        except (KeyError, IndexError) as exc:
            raise ValueError(
                "The provided skills_instruction_prompt is not a valid format string. "
                "It must contain a '{0}' placeholder and escape any literal '{' or '}' "
                "by doubling them ('{{' or '}}')."
            ) from exc

    if not skills:
        return None

    lines: list[str] = []
    # Sort by name for deterministic output
    for skill in sorted(skills.values(), key=lambda s: s.frontmatter.name):
        lines.append("  <skill>")
        lines.append(f"    <name>{xml_escape(skill.frontmatter.name)}</name>")
        lines.append(f"    <description>{xml_escape(skill.frontmatter.description)}</description>")
        lines.append("  </skill>")

    return template.format("\n".join(lines))

# endregion

# region Public API


class FileAgentSkillsProvider(BaseContextProvider):
    """A context provider that discovers and exposes Agent Skills from filesystem directories.

    This provider implements the progressive disclosure pattern from the
    `Agent Skills specification <https://agentskills.io/>`_:

    1. **Advertise** — skill names and descriptions are injected into the system prompt
       (~100 tokens per skill).
    2. **Load** — the full SKILL.md body is returned via the ``load_skill`` tool.
    3. **Read resources** — supplementary files are read on demand via the
       ``read_skill_resource`` tool.

    Skills are discovered by searching the configured directories for ``SKILL.md`` files.
    Referenced resources are validated at initialization; invalid skills are excluded and
    logged.

    **Security:** this provider only reads static content. Skill metadata is XML-escaped
    before prompt embedding, and resource reads are guarded against path traversal and
    symlink escape. Only use skills from trusted sources.

    Args:
        skill_paths: A single path or sequence of paths to search. Each can be an
            individual skill folder (containing a SKILL.md file) or a parent folder
            with skill subdirectories.

    Keyword Args:
        skills_instruction_prompt: A custom system prompt template for advertising
            skills. Use ``{0}`` as the placeholder for the generated skills list.
            When ``None``, a default template is used.
        source_id: Unique identifier for this provider instance.
        logger: Optional logger instance. When ``None``, uses the module logger.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "file_agent_skills"

    def __init__(
        self,
        skill_paths: str | Path | Sequence[str | Path],
        *,
        skills_instruction_prompt: str | None = None,
        source_id: str | None = None,
    ) -> None:
        """Initialize the FileAgentSkillsProvider.

        Args:
            skill_paths: A single path or sequence of paths to search for skills.

        Keyword Args:
            skills_instruction_prompt: Custom system prompt template with ``{0}`` placeholder.
            source_id: Unique identifier for this provider instance.
        """
        super().__init__(source_id or self.DEFAULT_SOURCE_ID)

        resolved_paths: Sequence[str] = [str(skill_paths)] if isinstance(skill_paths, (str, Path)) else [str(p) for p in skill_paths]

        self._skills = _discover_and_load_skills(resolved_paths)
        self._skills_instruction_prompt = _build_skills_instruction_prompt(skills_instruction_prompt, self._skills)
        self._tools = [
            FunctionTool(
                name="load_skill",
                description="Loads the full instructions for a specific skill.",
                func=self._load_skill,
                input_model={
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string", "description": "The name of the skill to load."},
                    },
                    "required": ["skill_name"],
                },
            ),
            FunctionTool(
                name="read_skill_resource",
                description="Reads a file associated with a skill, such as references or assets.",
                func=self._read_skill_resource,
                input_model={
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string", "description": "The name of the skill."},
                        "resource_name": {
                            "type": "string",
                            "description": "The relative path of the resource file.",
                        },
                    },
                    "required": ["skill_name", "resource_name"],
                },
            ),
        ]

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject skill instructions and tools into the session context.

        When skills are available, adds the skills instruction prompt and
        ``load_skill`` / ``read_skill_resource`` tools.
        """
        if not self._skills:
            return

        if self._skills_instruction_prompt:
            context.extend_instructions(self.source_id, self._skills_instruction_prompt)
        context.extend_tools(self.source_id, self._tools)

    def _load_skill(self, skill_name: str) -> str:
        """Load the full instructions for a specific skill.

        Args:
            skill_name: The name of the skill to load.

        Returns:
            The skill body text, or an error message if not found.
        """
        if not skill_name or not skill_name.strip():
            return "Error: Skill name cannot be empty."

        skill = self._skills.get(skill_name)
        if skill is None:
            return f"Error: Skill '{skill_name}' not found."

        logger.info("Loading skill: %s", skill_name)
        return skill.body

    def _read_skill_resource(self, skill_name: str, resource_name: str) -> str:
        """Read a file associated with a skill.

        Args:
            skill_name: The name of the skill.
            resource_name: The relative path of the resource file.

        Returns:
            The resource file content, or an error message if not found.
        """
        if not skill_name or not skill_name.strip():
            return "Error: Skill name cannot be empty."

        if not resource_name or not resource_name.strip():
            return "Error: Resource name cannot be empty."

        skill = self._skills.get(skill_name)
        if skill is None:
            return f"Error: Skill '{skill_name}' not found."

        try:
            return _read_skill_resource(skill, resource_name)
        except Exception:
            logger.exception("Failed to read resource '%s' from skill '%s'", resource_name, skill_name)
            return f"Error: Failed to read resource '{resource_name}' from skill '{skill_name}'."

# endregion
