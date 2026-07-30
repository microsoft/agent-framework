# Copyright (c) Microsoft. All rights reserved.

"""Agent Skills provider, models, and discovery utilities.

Defines the core data model classes for the agent skills system:

- **Skills:** :class:`Skill` (abstract base), :class:`InlineSkill` (code-defined),
  :class:`ClassSkill` (class-based), and :class:`FileSkill` (filesystem-backed).
- **Resources:** :class:`SkillResource` (abstract base), :class:`InlineSkillResource`
  (static content or callable).
- **Scripts:** :class:`SkillScript` (abstract base), :class:`InlineSkillScript`
  (in-process callable), and :class:`FileSkillScript` (file-path-backed).
- **Sources:** :class:`SkillsSource` (abstract base for custom skill origins).
- **Runner:** :class:`SkillScriptRunner` (protocol for executing file-based scripts).
- **Provider:** :class:`SkillsProvider` which implements the
  progressive-disclosure pattern from the
  `Agent Skills specification <https://agentskills.io/>`_:

1. **Advertise** — skill names and descriptions are injected into the system prompt.
2. **Load** — the full SKILL.md body is returned via the ``load_skill`` tool.
3. **Read resources** — supplementary content is returned on demand via
   the ``read_skill_resource`` tool.

Skills can come from different sources:

- **File-based** — discovered by scanning configured directories for ``SKILL.md`` files.
  Represented as :class:`FileSkill` instances.
- **Code-defined** — created as :class:`InlineSkill` instances in Python code,
  with optional callable resources attached via the ``@skill.resource`` decorator.
- **Class-based** — created by subclassing :class:`ClassSkill` to define
  self-contained, reusable skill types with ``create_resource()`` and
  ``create_script()`` factory methods.
- **Custom sources** — any :class:`SkillsSource` implementation that provides
  skills from arbitrary origins (REST APIs, databases, etc.).

Multiple sources can be composed using :class:`AggregatingSkillsSource`,
:class:`FilteringSkillsSource`, :class:`DeduplicatingSkillsSource`, and
:class:`CachingSkillsSource`.

**Security:** file-based skill metadata is XML-escaped before prompt injection, and
file-based resource reads are guarded against path traversal and symlink escape.
Only use skills from trusted sources.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from html import escape as xml_escape
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, ClassVar, Final, Protocol, TypeAlias, TypeVar, cast, runtime_checkable

from ._feature_stage import ExperimentalFeature, experimental
from ._sessions import ContextProvider
from ._telemetry import FeatureIndex, mark_feature_used
from ._tools import ApprovalMode, FunctionTool

if TYPE_CHECKING:
    from mcp.client.session import ClientSession
    from mcp.types import ReadResourceResult
    from pydantic import AnyUrl

    from ._agents import SupportsAgentRun
    from ._sessions import AgentSession, SessionContext
    from ._types import Content

logger = logging.getLogger(__name__)

# region Models


SkillScriptArgumentParser: TypeAlias = Callable[[dict[str, Any] | list[str] | str | None], dict[str, Any] | None]
"""Callable that converts raw script arguments before an inline script runs.

The parser receives the raw ``args`` value supplied by the agent/LLM (a
``dict`` of named arguments, a ``list[str]`` of positional arguments, a
``str`` for backends that send arguments as an unparsed JSON string, or
``None``) and returns the named keyword arguments to pass to the inline
script callable: a ``dict`` (or ``None`` for no arguments).  Inline scripts
bind arguments by keyword name, so the parser must normalize whatever shape
it receives into a ``dict`` or ``None``.

When no parser is configured, inline scripts use the raw value unchanged.
This hook lets callers plug in their own argument conversion logic to support
backends (for example, vLLM and some OpenAI-compatible servers) that encode
tool-call arguments as a JSON string instead of a JSON object.
"""


class SkillResource(ABC):
    """Abstract base class for supplementary content attached to a skill.

    A resource provides data that an agent can retrieve on demand.
    Concrete implementations handle either static/callable content
    or file-backed content read from disk.

    Attributes:
        name: Resource identifier.
        description: Optional human-readable summary, or ``None``.
    """

    def __init__(
        self,
        *,
        name: str,
        description: str | None = None,
    ) -> None:
        """Initialize a SkillResource.

        Args:
            name: Identifier for this resource (e.g. ``"reference"``, ``"get-schema"``).
            description: Optional human-readable summary shown when advertising the resource.
        """
        if not name or not name.strip():
            raise ValueError("Resource name cannot be empty.")

        self.name = name
        self.description = description

    @abstractmethod
    async def read(self, **kwargs: Any) -> Any:
        """Read the resource content.

        Args:
            **kwargs: Runtime keyword arguments forwarded to resource
                functions that accept ``**kwargs``.

        Returns:
            The resource content (any type).
        """


class InlineSkillResource(SkillResource):
    """A code-defined skill resource backed by static content or a callable.

    Holds either a static ``content`` string or a ``function`` that produces
    content dynamically (sync or async).  Exactly one must be provided.

    Attributes:
        name: Resource identifier.
        description: Optional human-readable summary, or ``None``.
        content: Static content string, or ``None`` if backed by a callable.
        function: Callable that returns content, or ``None`` if backed by static content.

    Examples:
        Static resource:

        .. code-block:: python

            InlineSkillResource(name="reference", content="Static docs here...")

        Callable resource:

        .. code-block:: python

            InlineSkillResource(name="schema", function=get_schema_func)
    """

    def __init__(
        self,
        *,
        name: str,
        description: str | None = None,
        content: str | None = None,
        function: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize an InlineSkillResource.

        Args:
            name: Identifier for this resource (e.g. ``"reference"``, ``"get-schema"``).
            description: Optional human-readable summary shown when advertising the resource.
            content: Static content string.  Mutually exclusive with *function*.
            function: Callable (sync or async) that returns content on demand.
                May return any type; the value is passed through as-is.
                Mutually exclusive with *content*.
        """
        super().__init__(name=name, description=description)

        if content is None and function is None:
            raise ValueError(f"Resource '{name}' must have either content or function.")
        if content is not None and function is not None:
            raise ValueError(f"Resource '{name}' must have either content or function, not both.")

        self.content = content
        self.function = function

        # Precompute whether the function accepts **kwargs to avoid
        # repeated inspect.signature() calls on every invocation.
        self._accepts_kwargs: bool = False
        if function is not None:
            sig = inspect.signature(function)
            self._accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())

    async def read(self, **kwargs: Any) -> Any:
        """Read the resource content.

        Returns static ``content`` directly.  For callable resources,
        invokes the function (awaiting if async) and returns the result.

        Args:
            **kwargs: Runtime keyword arguments forwarded to resource
                functions that accept ``**kwargs``.

        Returns:
            The resource content (any type).
        """
        if self.content is not None:
            return self.content

        func = cast(Callable[..., Any], self.function)
        result = func(**kwargs) if self._accepts_kwargs else func()
        if inspect.isawaitable(result):
            return await result
        return result


class _FileSkillResource(SkillResource):
    """A file-path-backed skill resource that reads content from disk.

    Stores a pre-resolved absolute file path and reads content directly,
    consistent with the sibling :class:`FileSkillScript`.

    Attributes:
        name: Resource identifier (relative path within the skill directory).
        description: Optional human-readable summary, or ``None``.
        full_path: Absolute path to the resource file.
    """

    def __init__(
        self,
        *,
        name: str,
        full_path: str,
        description: str | None = None,
    ) -> None:
        """Initialize a _FileSkillResource.

        Args:
            name: Relative path of the resource within the skill directory.
            full_path: Absolute path to the resource file.
            description: Optional human-readable summary.

        Raises:
            ValueError: If ``full_path`` is empty.
        """
        super().__init__(name=name, description=description)

        if not full_path or not full_path.strip():
            raise ValueError("full_path cannot be empty.")

        self.full_path = full_path

    async def read(self, **kwargs: Any) -> Any:
        """Read the resource content from disk.

        Args:
            **kwargs: Unused.

        Returns:
            The UTF-8 text content of the resource file.

        Raises:
            ValueError: If the resource file does not exist.
        """
        if not await asyncio.to_thread(Path(self.full_path).is_file):
            raise ValueError(f"Resource file '{self.name}' not found at '{self.full_path}'.")

        logger.info("Reading resource '%s' from '%s'", self.name, self.full_path)
        return await asyncio.to_thread(Path(self.full_path).read_text, encoding="utf-8")


class SkillScript(ABC):
    """Abstract base class for executable scripts attached to a skill.

    A script represents executable code that an agent can run.  Concrete
    implementations handle either code-defined scripts backed by a callable
    or file-path-backed scripts requiring an external runner.

    Attributes:
        name: Script identifier.
        description: Optional human-readable summary, or ``None``.
    """

    def __init__(
        self,
        *,
        name: str,
        description: str | None = None,
    ) -> None:
        """Initialize a SkillScript.

        Args:
            name: Identifier for this script (e.g. ``"analyze"``, ``"process.py"``).
            description: Optional human-readable summary.
        """
        if not name or not name.strip():
            raise ValueError("Script name cannot be empty.")

        self.name = name
        self.description = description

    @property
    def parameters_schema(self) -> dict[str, Any] | None:
        """JSON Schema describing the script's parameters, or ``None``."""
        return None

    @abstractmethod
    async def run(self, skill: Skill, args: dict[str, Any] | list[str] | None = None, **kwargs: Any) -> Any:
        """Run this script.

        Args:
            skill: The skill that owns this script.
            args: Optional arguments for the script, provided by the
                agent/LLM.  May be a ``dict`` (named keyword arguments
                for inline scripts) or a ``list[str]`` (positional CLI
                arguments for file-based scripts).
            **kwargs: Runtime keyword arguments forwarded only to script
                functions that accept ``**kwargs``.

        Returns:
            The script execution result.
        """


class InlineSkillScript(SkillScript):
    """A code-defined skill script backed by a callable.

    The callable is invoked directly in-process when the script is run.
    Parameters schema is lazily generated from the callable's signature.

    Attributes:
        name: Script identifier.
        description: Optional human-readable summary, or ``None``.
        function: Callable that implements the script.

    Examples:
        .. code-block:: python

            InlineSkillScript(name="analyze", function=analyze_data, description="Run analysis")
    """

    def __init__(
        self,
        *,
        name: str,
        description: str | None = None,
        function: Callable[..., Any],
        argument_parser: SkillScriptArgumentParser | None = None,
    ) -> None:
        """Initialize an InlineSkillScript.

        Args:
            name: Identifier for this script (e.g. ``"analyze"``).
            description: Optional human-readable summary.
            function: Callable (sync or async) that implements the script.
            argument_parser: Optional callable that converts the raw
                ``args`` value into the named arguments passed to
                ``function`` before the script runs.  When ``None`` (the
                default), the raw value is used unchanged, which expects a
                ``dict`` (or ``None``).  Supply a parser to support
                backends that send arguments in a non-conforming shape (for
                example, vLLM-style JSON strings).
        """
        super().__init__(name=name, description=description)

        self.function = function
        self.argument_parser = argument_parser
        self._parameters_schema: dict[str, Any] | None = None
        self._parameters_schema_resolved: bool = False

        # Precompute whether the function accepts **kwargs to avoid
        # repeated inspect.signature() calls on every invocation.
        sig = inspect.signature(function)
        self._accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())

    @property
    def parameters_schema(self) -> dict[str, Any] | None:
        """JSON Schema describing the script's parameters.

        Lazily generated from the callable's signature on first access.
        Returns ``None`` for functions with no introspectable parameters.
        """
        if not self._parameters_schema_resolved:
            tool = FunctionTool(name=self.function.__name__, func=self.function)
            schema = tool.parameters()
            self._parameters_schema = schema if schema and schema.get("properties") else None
            self._parameters_schema_resolved = True
        return self._parameters_schema

    async def run(self, skill: Skill, args: dict[str, Any] | list[str] | str | None = None, **kwargs: Any) -> Any:
        """Run the script by invoking the callable in-process.

        When an ``argument_parser`` is configured, it is applied to
        ``args`` first to convert it into the named arguments for the
        callable.  Otherwise ``args`` is used unchanged.

        Args:
            skill: The skill that owns this script.
            args: Optional keyword arguments for the script, provided by the
                agent/LLM.  May be a raw ``str`` when an
                ``argument_parser`` is configured to convert it.  After
                any configured ``argument_parser`` runs, the result must
                be a ``dict`` or ``None``; a ``list`` raises
                :class:`TypeError` because inline scripts bind arguments by
                keyword name.
            **kwargs: Runtime keyword arguments forwarded only to script
                functions that accept ``**kwargs``.

        Returns:
            The script execution result.

        Raises:
            TypeError: If ``args`` (after parsing) is a ``str`` or a
                ``list``.  A leftover ``str`` means no ``argument_parser``
                converted it; a ``list`` is array-style and only supported
                for file-based scripts.
        """
        if self.argument_parser is not None:
            args = self.argument_parser(args)
        if isinstance(args, str):
            raise TypeError(
                f"Inline script '{self.name}' received string arguments that were not "
                f"converted to a dict. Configure an 'argument_parser' to convert "
                f"string-encoded arguments into named keyword arguments."
            )
        if isinstance(args, list):
            raise TypeError(
                f"Inline script '{self.name}' requires keyword arguments (dict), "
                f"but received a list. Array-style arguments are only supported "
                f"for file-based scripts."
            )
        if self._accepts_kwargs:  # ruff:ignore[if-else-block-instead-of-if-exp]
            result = self.function(**(args or {}), **kwargs)
        else:
            result = self.function(**(args or {}))
        if inspect.isawaitable(result):
            return await result
        return result


class FileSkillScript(SkillScript):
    """A file-path-backed skill script requiring an external runner.

    Represents a script file on disk that is delegated to a configured
    :class:`SkillScriptRunner` for execution.

    Attributes:
        name: Script identifier.
        description: Optional human-readable summary, or ``None``.
        full_path: Absolute path to the script file.

    Examples:
        .. code-block:: python

            FileSkillScript(name="process.py", full_path="/skills/my-skill/scripts/process.py")
    """

    def __init__(
        self,
        *,
        name: str,
        description: str | None = None,
        full_path: str,
        runner: SkillScriptRunner | None = None,
    ) -> None:
        """Initialize a FileSkillScript.

        Args:
            name: Identifier for this script (e.g. ``"process.py"``).
            description: Optional human-readable summary.
            full_path: Absolute path to the script file.
            runner: Strategy for running file-based scripts.  Required for
                execution; an error is raised from :meth:`run` if not provided.

        Raises:
            ValueError: If ``full_path`` is empty or not an absolute path.
        """
        super().__init__(name=name, description=description)

        if not full_path or not full_path.strip():
            raise ValueError("full_path cannot be empty.")
        if not os.path.isabs(full_path):
            raise ValueError(f"full_path must be an absolute path, got: '{full_path}'")

        self.full_path = full_path
        self._runner = runner

    @property
    def parameters_schema(self) -> dict[str, Any] | None:
        """JSON Schema advertising that file scripts accept a string array.

        Returns a fixed schema ``{"type": "array", "items": {"type": "string"}}``
        so that the LLM knows to pass positional CLI arguments as a JSON array
        of strings.
        """
        return {"type": "array", "items": {"type": "string"}}

    async def run(self, skill: Skill, args: dict[str, Any] | list[str] | None = None, **kwargs: Any) -> Any:
        """Run the script by delegating to the configured runner.

        Args:
            skill: The skill that owns this script.  Must be a
                :class:`FileSkill`.
            args: Optional arguments for the script.
            **kwargs: Additional runtime keyword arguments (unused).

        Returns:
            The script execution result.

        Raises:
            TypeError: If ``skill`` is not a :class:`FileSkill`.
            ValueError: If no runner was provided.
        """
        if not isinstance(skill, FileSkill):
            raise TypeError(
                f"File-based script '{self.name}' requires a FileSkill but received '{type(skill).__name__}'."
            )
        if self._runner is None:
            raise ValueError(f"Script '{self.name}' requires a runner. Provide a script_runner for file-based scripts.")
        result = self._runner(skill, self, args)
        if inspect.isawaitable(result):
            return await result
        return result


class Skill(ABC):
    """Abstract base class for all agent skills.

    A skill represents a domain-specific capability with instructions,
    resources, and scripts.  Concrete implementations include
    :class:`FileSkill` (filesystem-backed), :class:`InlineSkill`
    (code-defined), and :class:`ClassSkill` (class-based).

    Skill spec metadata (name, description, license, compatibility,
    allowed_tools, metadata) is exposed via the :attr:`frontmatter`
    property, which returns a :class:`SkillFrontmatter` instance.
    """

    @property
    @abstractmethod
    def frontmatter(self) -> SkillFrontmatter:
        """The L1 discovery metadata for this skill.

        Contains the name, description, and other spec fields as defined by
        the `Agent Skills specification <https://agentskills.io/specification>`_.
        """
        ...

    @abstractmethod
    async def get_content(self) -> str:
        """Get the full skill content.

        For file-based skills this is the raw SKILL.md file content,
        optionally augmented with a synthesized scripts block when scripts
        are present.  For code-defined skills this is a synthesized XML
        document containing name, description, and body (instructions,
        resources, scripts).

        Returns:
            The full skill content string.
        """
        ...

    async def get_resource(self, name: str) -> SkillResource | None:
        """Get a resource owned by this skill by name.

        Args:
            name: The resource name (e.g. an identifier or a relative path
                referenced inside the skill content).

        Returns:
            The :class:`SkillResource`, or ``None`` when no resource with the
            given name exists.
        """
        return None

    async def get_script(self, name: str) -> SkillScript | None:
        """Get a script owned by this skill by name.

        Args:
            name: The script name.

        Returns:
            The :class:`SkillScript`, or ``None`` when no script with the
            given name exists.
        """
        return None


class SkillFrontmatter:
    """L1 discovery metadata for a :class:`Skill`.

    Encapsulates all `Agent Skills specification <https://agentskills.io/specification>`_
    frontmatter fields in a single object. All fields are mutable plain
    attributes; callers may freely reassign them after construction.

    The constructor validates ``name``, ``description``, and ``compatibility``
    against specification rules and raises :class:`ValueError` on invalid
    input. Assignments made after construction are **not** re-validated;
    callers are expected to honor the spec.

    Attributes:
        name: Skill name (lowercase letters, numbers, hyphens only).
        description: Human-readable description of the skill.
        license: Optional license name or reference.
        compatibility: Optional compatibility information (≤500 characters).
        allowed_tools: Optional space-delimited pre-approved tool names.
        metadata: Optional arbitrary key-value pairs (shallow-copied on
            construction to avoid caller-owned dict aliasing).
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        license: str | None = None,
        compatibility: str | None = None,
        allowed_tools: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Initialize a SkillFrontmatter.

        Args:
            name: Skill name (lowercase letters, numbers, hyphens only;
                max 64 characters; no leading/trailing/consecutive hyphens).
            description: Human-readable description of the skill
                (≤1024 characters).
            license: Optional license name or reference.
            compatibility: Optional compatibility information
                (≤500 characters).
            allowed_tools: Optional space-delimited pre-approved tool names.
            metadata: Optional arbitrary key-value pairs.

        Raises:
            ValueError: If the name, description, or compatibility is invalid.
        """
        _validate_skill_name(name)
        _validate_skill_description(name, description)
        _validate_compatibility(compatibility)

        self.name = name
        self.description = description
        self.compatibility = compatibility
        self.license = license
        self.allowed_tools = allowed_tools
        # Shallow-copy to avoid aliasing with caller-owned dict.
        self.metadata: dict[str, str] | None = dict(metadata) if metadata is not None else None


def _validate_skill_name(name: str) -> None:
    """Validate a skill name against specification rules.

    Args:
        name: The skill name to validate.

    Raises:
        ValueError: If the name is empty, too long, or does not match
            the required pattern.
    """
    if not name or not name.strip():
        raise ValueError("Skill name cannot be empty.")
    if len(name) > MAX_NAME_LENGTH or not VALID_NAME_RE.match(name):
        raise ValueError(
            f"Invalid skill name '{name}': Must be {MAX_NAME_LENGTH} characters or fewer, "
            "using only lowercase letters, numbers, and hyphens, and must not start or end with a hyphen "
            "or contain consecutive hyphens."
        )


def _validate_skill_description(name: str, description: str) -> None:
    """Validate a skill description against specification rules.

    Args:
        name: The skill name (used in error messages).
        description: The description to validate.

    Raises:
        ValueError: If the description is empty or too long.
    """
    if not description or not description.strip():
        raise ValueError("Skill description cannot be empty.")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(
            f"Skill '{name}' has an invalid description: Must be {MAX_DESCRIPTION_LENGTH} characters or fewer."
        )


def _validate_compatibility(compatibility: str | None) -> None:
    """Validate an optional compatibility value against specification rules.

    Args:
        compatibility: The optional compatibility value to validate.

    Raises:
        ValueError: If the value exceeds the maximum allowed length.
    """
    if compatibility is not None and len(compatibility) > MAX_COMPATIBILITY_LENGTH:
        raise ValueError(f"Skill compatibility must be {MAX_COMPATIBILITY_LENGTH} characters or fewer.")


def _build_skill_content(
    name: str,
    description: str,
    instructions: str,
    resources: Sequence[SkillResource] | None = None,
    scripts: Sequence[SkillScript] | None = None,
) -> str:
    """Build XML-structured content for code-defined and class-based skills.

    Produces an XML document containing name, description, instructions, and
    ``<available_resources>`` / ``<available_scripts>`` blocks.  The two blocks
    are always emitted: when a category has no entries, a self-closing element
    (e.g. ``<available_scripts />``) is emitted so the model knows none are
    available and does not hallucinate their names.  Used by both
    :class:`InlineSkill` and :class:`ClassSkill` to generate their ``content``
    property.

    Args:
        name: The skill name.
        description: The skill description.
        instructions: The raw instructions text.
        resources: Optional resources associated with the skill.
        scripts: Optional scripts associated with the skill.

    Returns:
        An XML-structured content string.
    """
    result = (
        f"<name>{xml_escape(name)}</name>\n"
        f"<description>{xml_escape(description)}</description>\n"
        "\n"
        "<instructions>\n"
        f"{instructions}\n"
        "</instructions>"
    )

    result += f"\n\n{_build_available_resources_block(resources)}"
    result += f"\n\n{_build_available_scripts_block(scripts)}"

    return result


def _create_resource_element(resource: SkillResource) -> str:
    """Create a self-closing ``<resource …/>`` XML element from a :class:`SkillResource`.

    Args:
        resource: The resource to create the element from.

    Returns:
        A single indented XML element string with ``name`` and optional
        ``description`` attributes.
    """
    attrs = f'name="{xml_escape(resource.name, quote=True)}"'
    if resource.description:
        attrs += f' description="{xml_escape(resource.description, quote=True)}"'
    return f"  <resource {attrs}/>"


def _build_available_resources_block(resources: Sequence[SkillResource] | None) -> str:
    """Build an ``<available_resources>`` XML block for the given resources.

    Each resource is emitted as a ``<resource name="…"/>`` element (with an
    optional ``description`` attribute).  When there are no resources, a
    self-closing ``<available_resources />`` element is returned so the model
    knows none are available and does not hallucinate resource names.

    Args:
        resources: The resources to include in the block, if any.

    Returns:
        The ``<available_resources>`` XML block, or ``<available_resources />``
        when *resources* is empty or ``None``.
    """
    if not resources:
        return "<available_resources />"
    resource_lines = "\n".join(_create_resource_element(r) for r in resources)
    return f"<available_resources>\n{resource_lines}\n</available_resources>"


def _build_available_scripts_block(scripts: Sequence[SkillScript] | None) -> str:
    """Build an ``<available_scripts>`` XML block for the given scripts.

    Each script is emitted as a ``<script name="…">`` element; when the script
    has a parameter schema it is wrapped in a nested ``<parameters_schema>``
    element, otherwise a self-closing ``<script …/>`` element is used.  When
    there are no scripts, a self-closing ``<available_scripts />`` element is
    returned so the model knows none are available and does not hallucinate
    script names.

    Args:
        scripts: The scripts to include in the block, if any.

    Returns:
        The ``<available_scripts>`` XML block, or ``<available_scripts />``
        when *scripts* is empty or ``None``.
    """
    if not scripts:
        return "<available_scripts />"
    script_lines = "\n".join(_create_script_element(s) for s in scripts)
    return f"<available_scripts>\n{script_lines}\n</available_scripts>"


class InlineSkill(Skill):
    """A skill defined entirely in code with resources and scripts.

    All resources and scripts should be configured before the skill is
    registered with a :class:`SkillsProvider`.

    Examples:
        .. code-block:: python

            skill = InlineSkill(
                frontmatter=SkillFrontmatter(
                    name="db-skill",
                    description="Database operations",
                ),
                instructions="Use this skill for DB tasks.",
            )


            @skill.resource
            def get_schema() -> str:
                return "CREATE TABLE ..."
    """

    def __init__(
        self,
        *,
        frontmatter: SkillFrontmatter,
        instructions: str,
        resources: Sequence[SkillResource] | None = None,
        scripts: Sequence[SkillScript] | None = None,
        argument_parser: SkillScriptArgumentParser | None = None,
    ) -> None:
        """Initialize an InlineSkill.

        Args:
            frontmatter: Skill specification metadata (name, description,
                and optional spec fields). Construct a :class:`SkillFrontmatter`
                with the desired fields.
            instructions: The skill instructions text.
            resources: Pre-built resources to attach to this skill.
            scripts: Pre-built scripts to attach to this skill.
            argument_parser: Optional default :data:`SkillScriptArgumentParser`
                applied to scripts registered via the :meth:`script` decorator.
                Pre-built ``scripts`` keep their own parser. When ``None``
                (the default), scripts use the raw argument value unchanged.
        """
        self._frontmatter = frontmatter

        self.instructions = instructions
        self._argument_parser = argument_parser
        self._resources: list[SkillResource] = list(resources) if resources is not None else []
        self._scripts: list[SkillScript] = list(scripts) if scripts is not None else []
        self._cached_content: str | None = None

    @property
    def frontmatter(self) -> SkillFrontmatter:
        """The L1 discovery metadata for this skill."""
        return self._frontmatter

    async def get_content(self) -> str:
        """Synthesized XML content with name, description, instructions, resources, and scripts.

        The ``<available_resources>`` and ``<available_scripts>`` blocks are
        always emitted; an empty category is rendered as a self-closing element
        (e.g. ``<available_scripts />``) so the model knows none are available.

        The result is cached after the first access.  Adding resources or
        scripts after the first access will not be reflected.

        Returns:
            The synthesized XML content string.
        """
        if self._cached_content is not None:
            return self._cached_content

        self._cached_content = _build_skill_content(
            self._frontmatter.name,
            self._frontmatter.description,
            self.instructions,
            self._resources,
            self._scripts,
        )
        return self._cached_content

    async def get_resource(self, name: str) -> SkillResource | None:
        """Get a resource by name.

        Args:
            name: The resource name to look up (case-insensitive).

        Returns:
            The :class:`SkillResource`, or ``None`` when no resource with the
            given name exists.
        """
        name_lower = name.lower()
        return next((r for r in self._resources if r.name.lower() == name_lower), None)

    async def get_script(self, name: str) -> SkillScript | None:
        """Get a script by name.

        Args:
            name: The script name to look up (case-insensitive).

        Returns:
            The :class:`SkillScript`, or ``None`` when no script with the
            given name exists.
        """
        name_lower = name.lower()
        return next((s for s in self._scripts if s.name.lower() == name_lower), None)

    def resource(
        self,
        func: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Any:
        """Decorator that registers a callable as a resource on this skill.

        Supports bare usage (``@skill.resource``) and parameterized usage
        (``@skill.resource(name="custom", description="...")``).  The
        decorated function is returned unchanged; a new
        :class:`SkillResource` is appended to :attr:`resources`.

        Args:
            func: The function being decorated.  Populated automatically when
                the decorator is applied without parentheses.

        Keyword Args:
            name: Resource name override.  Defaults to ``func.__name__``.
            description: Resource description override.  Defaults to ``None``.

        Returns:
            The original function unchanged, or a secondary decorator when
            called with keyword arguments.

        Examples:
            Bare decorator:

            .. code-block:: python

                @skill.resource
                def get_schema() -> Any:
                    return "schema..."

            With arguments:

            .. code-block:: python

                @skill.resource(name="custom-name", description="Custom desc")
                async def get_data() -> Any:
                    return "data..."
        """

        def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
            resource_name = name or f.__name__
            resource_description = description
            self._resources.append(
                InlineSkillResource(
                    name=resource_name,
                    description=resource_description,
                    function=f,
                )
            )
            return f

        if func is None:
            return decorator
        return decorator(func)

    def script(
        self,
        func: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Any:
        """Decorator that registers a callable as a script on this skill.

        Supports bare usage (``@skill.script``) and parameterized usage
        (``@skill.script(name="custom", description="...")``).  The
        decorated function is returned unchanged; a new
        :class:`SkillScript` is appended to :attr:`scripts`.

        Args:
            func: The function being decorated.  Populated automatically when
                the decorator is applied without parentheses.

        Keyword Args:
            name: Script name override.  Defaults to ``func.__name__``.
            description: Script description override.  Defaults to ``None``.

        Returns:
            The original function unchanged, or a secondary decorator when
            called with keyword arguments.

        Examples:
            Bare decorator:

            .. code-block:: python

                @skill.script
                def analyze_data(query: str) -> str:
                    \"\"\"Run data analysis.\"\"\"
                    return run_analysis(query)

            With arguments:

            .. code-block:: python

                @skill.script(name="fetch", description="Fetch remote data")
                async def fetch_data(url: str) -> str:
                    return await http_get(url)
        """

        def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
            script_name = name or f.__name__
            script_description = description
            self._scripts.append(
                InlineSkillScript(
                    name=script_name,
                    description=script_description,
                    function=f,
                    argument_parser=self._argument_parser,
                )
            )
            return f

        if func is None:
            return decorator
        return decorator(func)


def _make_method_name(method_name: str) -> str:
    """Convert a Python method name to a skill resource/script name.

    Replaces underscores with hyphens to match the skill naming convention.

    Args:
        method_name: The Python method name (e.g. ``"conversion_table"``).

    Returns:
        The converted name (e.g. ``"conversion-table"``).
    """
    return method_name.replace("_", "-").strip("-")


def _validate_member_name(name: str, kind: str) -> None:
    """Validate a resource or script name at decoration time.

    Args:
        name: The name to validate.
        kind: ``"resource"`` or ``"script"`` — used in error messages.

    Raises:
        ValueError: If the name is empty, too long, or contains invalid characters.
    """
    if not name or not name.strip():
        raise ValueError(f"@ClassSkill.{kind} name cannot be empty.")
    if len(name) > MAX_NAME_LENGTH or not VALID_NAME_RE.match(name):
        raise ValueError(
            f"Invalid @ClassSkill.{kind} name '{name}': Must be {MAX_NAME_LENGTH} characters or fewer, "
            "using only lowercase letters, numbers, and hyphens, and must not start or end with a hyphen "
            "or contain consecutive hyphens."
        )


def _discover_marked_members(cls: type, marker_attr: str) -> list[tuple[str, dict[str, Any]]]:
    """Scan a class for methods or properties stamped with a marker attribute.

    Checks both regular callable attributes (via ``dir``) and ``property``
    descriptors (via ``cls.__dict__``) whose ``fget`` carries the marker.

    Args:
        cls: The class to scan.
        marker_attr: The marker attribute name to look for (e.g.
            ``"_skill_resource_marker"``).

    Returns:
        A list of ``(member_name, marker_dict)`` tuples.
    """
    results: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()

    # Walk the MRO so that property-resources defined on a parent class
    # are also discovered.  ``cls.__dict__`` only sees the leaf class.
    for klass in cls.__mro__:
        for attr_name, attr_value in klass.__dict__.items():
            if attr_name in seen:
                continue
            if (
                isinstance(attr_value, property)
                and attr_value.fget is not None
                and hasattr(attr_value.fget, marker_attr)
            ):
                results.append((attr_name, getattr(attr_value.fget, marker_attr)))
                seen.add(attr_name)

    # Check regular callable attributes.
    for attr_name in dir(cls):
        if attr_name in seen:
            continue
        try:
            attr = getattr(cls, attr_name, None)
        except Exception:
            # Some descriptors (e.g. abstract properties) may raise on access.
            logger.warning("Skipping '%s' during skill discovery: descriptor raised on access", attr_name)
            attr = None
        if attr is not None and callable(attr) and hasattr(attr, marker_attr):
            results.append((attr_name, getattr(attr, marker_attr)))
    return results


class ClassSkill(Skill, ABC):
    """Abstract base class for defining skills as reusable Python classes.

    Inherit from this class to create a self-contained skill definition.
    Override :attr:`instructions` to provide the skill body.

    Resources and scripts can be defined in two ways:

    - **Decorator-based (recommended):** Mark methods with
      :meth:`ClassSkill.resource` and :meth:`ClassSkill.script` decorators
      for automatic discovery.
    - **Explicit override:** Override the :attr:`resources` and
      :attr:`scripts` properties, constructing :class:`InlineSkillResource`
      and :class:`InlineSkillScript` instances directly.

    Class-based skills can be distributed via shared libraries or PyPI
    packages, making them easy to reuse across projects.

    Examples:
        Decorator-based (recommended):

        .. code-block:: python

            class UnitConverterSkill(ClassSkill):
                def __init__(self) -> None:
                    super().__init__(
                        frontmatter=SkillFrontmatter(
                            name="unit-converter",
                            description="Convert between common units.",
                        ),
                    )

                @property
                def instructions(self) -> str:
                    return "Use this skill to convert units..."

                @ClassSkill.resource(name="table")
                def conversion_table(self) -> str:
                    return "| From | To | Factor |..."

                @ClassSkill.script(name="convert")
                def convert(self, value: float, factor: float) -> str:
                    return json.dumps({"result": round(value * factor, 4)})

        Explicit override:

        .. code-block:: python

            class UnitConverterSkill(ClassSkill):
                def __init__(self) -> None:
                    super().__init__(
                        frontmatter=SkillFrontmatter(
                            name="unit-converter",
                            description="Convert between common units.",
                        ),
                    )

                @property
                def instructions(self) -> str:
                    return "Use this skill to convert units..."

                @property
                def resources(self) -> list[SkillResource]:
                    return [
                        InlineSkillResource(name="table", content="| From | To | Factor |..."),
                    ]

                @property
                def scripts(self) -> list[SkillScript]:
                    return [InlineSkillScript(name="convert", function=convert_fn)]
    """

    def __init__(
        self,
        *,
        frontmatter: SkillFrontmatter,
        argument_parser: SkillScriptArgumentParser | None = None,
    ) -> None:
        """Initialize a ClassSkill.

        Args:
            frontmatter: Skill specification metadata (name, description,
                and optional spec fields). Construct a :class:`SkillFrontmatter`
                with the desired fields.
            argument_parser: Optional default :data:`SkillScriptArgumentParser`
                applied to scripts discovered from :meth:`ClassSkill.script`-decorated
                methods. When ``None`` (the default), discovered scripts use the
                raw argument value unchanged.
        """
        self._frontmatter = frontmatter
        self._argument_parser = argument_parser
        self._cached_content: str | None = None
        self._cached_resources: list[SkillResource] | None = None
        self._cached_scripts: list[SkillScript] | None = None

    @property
    def frontmatter(self) -> SkillFrontmatter:
        """The L1 discovery metadata for this skill."""
        return self._frontmatter

    @staticmethod
    def resource(
        func: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Any:
        """Decorator that marks a method or property as a skill resource for auto-discovery.

        When applied to a method or property on a :class:`ClassSkill` subclass,
        it is automatically discovered and registered as an
        :class:`InlineSkillResource`.  Methods are invoked each time the
        resource is read.  Properties are evaluated via their getter.

        Can be applied to a method directly, or stacked with ``@property``
        (place ``@property`` first, ``@ClassSkill.resource`` second).

        Supports bare usage (``@ClassSkill.resource``) and parameterized usage
        (``@ClassSkill.resource(name="custom", description="...")``).

        Args:
            func: The function being decorated.  Populated automatically when
                the decorator is applied without parentheses.

        Keyword Args:
            name: Resource name override.  Defaults to the method name with
                underscores replaced by hyphens.
            description: Resource description.  Defaults to ``None``.

        Examples:
            On a method:

            .. code-block:: python

                @ClassSkill.resource(name="conversion-table")
                def get_table(self) -> str:
                    return "..."

            On a property:

            .. code-block:: python

                @property
                @ClassSkill.resource
                def conversion_table(self) -> str:
                    return "..."
        """

        def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
            if isinstance(f, (property, classmethod, staticmethod)):
                raise TypeError(
                    "@ClassSkill.resource must be applied before @property, @classmethod, or @staticmethod. "
                    "Place @property first, then @ClassSkill.resource."
                )
            if name is not None:
                _validate_member_name(name, "resource")
            f._skill_resource_marker = {  # type: ignore[attr-defined]
                "name": name,
                "description": description,
            }
            return f

        if func is None:
            return decorator
        return decorator(func)

    @staticmethod
    def script(
        func: Callable[..., Any] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Any:
        """Decorator that marks a method as a skill script for auto-discovery.

        When applied to a method on a :class:`ClassSkill` subclass, the method is
        automatically discovered and registered as an :class:`InlineSkillScript`.
        The method's parameters (excluding ``self``) are used to generate a JSON
        schema, and the method is invoked in-process when the script is run.

        Supports bare usage (``@ClassSkill.script``) and parameterized usage
        (``@ClassSkill.script(name="custom", description="...")``).

        Args:
            func: The function being decorated.  Populated automatically when
                the decorator is applied without parentheses.

        Keyword Args:
            name: Script name override.  Defaults to the method name with
                underscores replaced by hyphens.
            description: Script description.  Defaults to ``None``.

        Examples:
            .. code-block:: python

                @ClassSkill.script(name="convert")
                def convert(self, value: float, factor: float) -> str:
                    return json.dumps({"result": round(value * factor, 4)})
        """

        def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
            if isinstance(f, (property, classmethod, staticmethod)):
                raise TypeError("@ClassSkill.script must be applied before @property, @classmethod, or @staticmethod.")
            if name is not None:
                _validate_member_name(name, "script")
            f._skill_script_marker = {  # type: ignore[attr-defined]
                "name": name,
                "description": description,
            }
            return f

        if func is None:
            return decorator
        return decorator(func)

    @property
    @abstractmethod
    def instructions(self) -> str:
        """The raw instructions text for this skill.

        Subclasses must override this property to provide the skill body.
        """
        ...

    @property
    def resources(self) -> list[SkillResource]:
        """Resources discovered from :meth:`ClassSkill.resource`-decorated methods.

        On first access, scans the class for methods marked with the
        :meth:`ClassSkill.resource` decorator and instantiates
        :class:`InlineSkillResource` instances from them.
        The result is cached after the first access.

        Override this property to provide resources explicitly instead of
        using decorator-based discovery.
        """
        if self._cached_resources is not None:
            return list(self._cached_resources)

        resources: list[SkillResource] = []
        seen_names: set[str] = set()

        for attr_name, attr in _discover_marked_members(type(self), "_skill_resource_marker"):
            marker: dict[str, Any] = attr
            resource_name = marker.get("name") or _make_method_name(attr_name)
            if resource_name in seen_names:
                raise ValueError(
                    f"Skill '{self._frontmatter.name}' already has a resource named '{resource_name}'. "
                    "Ensure each @ClassSkill.resource has a unique name."
                )
            seen_names.add(resource_name)

            # Use inspect.getattr_static to check the descriptor type without
            # triggering it, and walk the MRO so inherited properties are found.
            static_attr = inspect.getattr_static(self, attr_name, None)
            is_property = isinstance(static_attr, property)
            resource_description = marker.get("description")

            if is_property:
                # Property — use a lambda that reads the property value each time.
                # We capture attr_name to avoid late-binding issues.
                # Do NOT call getattr here to avoid triggering the getter during discovery.
                resource_func = (lambda name: lambda: getattr(self, name))(attr_name)
                resources.append(
                    InlineSkillResource(
                        name=resource_name,
                        function=resource_func,
                        description=resource_description,
                    )
                )
            else:
                # Regular method — use the bound method directly.
                bound_method = getattr(self, attr_name)
                resources.append(
                    InlineSkillResource(
                        name=resource_name,
                        function=bound_method,
                        description=resource_description,
                    )
                )

        self._cached_resources = resources
        return list(self._cached_resources)

    @property
    def scripts(self) -> list[SkillScript]:
        """Scripts discovered from :meth:`ClassSkill.script`-decorated methods.

        On first access, scans the class for methods marked with the
        :meth:`ClassSkill.script` decorator and instantiates
        :class:`InlineSkillScript` instances from them.
        The result is cached after the first access.

        Override this property to provide scripts explicitly instead of
        using decorator-based discovery.
        """
        if self._cached_scripts is not None:
            return list(self._cached_scripts)

        scripts: list[SkillScript] = []
        seen_names: set[str] = set()

        for attr_name, attr in _discover_marked_members(type(self), "_skill_script_marker"):
            marker: dict[str, Any] = attr
            script_name = marker.get("name") or _make_method_name(attr_name)
            if script_name in seen_names:
                raise ValueError(
                    f"Skill '{self._frontmatter.name}' already has a script named '{script_name}'. "
                    "Ensure each @ClassSkill.script has a unique name."
                )
            seen_names.add(script_name)

            bound_method = getattr(self, attr_name)
            script_description = marker.get("description")
            scripts.append(
                InlineSkillScript(
                    name=script_name,
                    function=bound_method,
                    description=script_description,
                    argument_parser=self._argument_parser,
                )
            )

        self._cached_scripts = scripts
        return list(self._cached_scripts)

    async def get_content(self) -> str:
        """Synthesized XML content containing name, description, instructions, resources, and scripts.

        The ``<available_resources>`` and ``<available_scripts>`` blocks are
        always emitted; an empty category is rendered as a self-closing element
        (e.g. ``<available_scripts />``) so the model knows none are available.

        The result is cached after the first access.

        Returns:
            The synthesized XML content string.
        """
        if self._cached_content is not None:
            return self._cached_content

        self._cached_content = _build_skill_content(
            self._frontmatter.name,
            self._frontmatter.description,
            self.instructions,
            self.resources,
            self.scripts,
        )
        return self._cached_content

    async def get_resource(self, name: str) -> SkillResource | None:
        """Get a resource by name from the :attr:`resources` list.

        Args:
            name: The resource name to look up (case-insensitive).

        Returns:
            The :class:`SkillResource`, or ``None`` when no resource with the
            given name exists.
        """
        name_lower = name.lower()
        return next((r for r in self.resources if r.name.lower() == name_lower), None)

    async def get_script(self, name: str) -> SkillScript | None:
        """Get a script by name from the :attr:`scripts` list.

        Args:
            name: The script name to look up (case-insensitive).

        Returns:
            The :class:`SkillScript`, or ``None`` when no script with the
            given name exists.
        """
        name_lower = name.lower()
        return next((s for s in self.scripts if s.name.lower() == name_lower), None)


class FileSkill(Skill):
    """A :class:`Skill` discovered from a filesystem directory backed by a SKILL.md file.

    Attributes:
        path: Absolute path to the directory containing this skill.
    """

    def __init__(
        self,
        *,
        frontmatter: SkillFrontmatter,
        content: str,
        path: str,
        resources: Sequence[SkillResource] | None = None,
        scripts: Sequence[SkillScript] | None = None,
    ) -> None:
        """Initialize a FileSkill.

        Args:
            frontmatter: Skill specification metadata parsed from the
                SKILL.md file's YAML frontmatter (name, description,
                and optional spec fields).
            content: The full raw SKILL.md file content including YAML frontmatter.
            path: Absolute path to the skill directory on disk.
            resources: Resources discovered for this skill.
            scripts: Scripts discovered for this skill.
        """
        self._frontmatter = frontmatter

        self._content = content
        self.path = path
        self._resources: list[SkillResource] = list(resources) if resources is not None else []
        self._scripts: list[SkillScript] = list(scripts) if scripts is not None else []
        self._cached_content: str | None = None

    @property
    def frontmatter(self) -> SkillFrontmatter:
        """The L1 discovery metadata for this skill."""
        return self._frontmatter

    async def get_content(self) -> str:
        """The skill content with appended resource and script blocks.

        The raw SKILL.md content is followed by ``<available_resources>`` and
        ``<available_scripts>`` blocks.  Both are always emitted: a category
        with no entries is appended as a self-closing element (e.g.
        ``<available_scripts />``) so the model knows none are available and
        does not hallucinate their names.  When entries are present, scripts
        include their ``<parameters_schema>`` so the LLM can discover the
        argument format.

        The result is cached after the first access.  Adding resources or
        scripts after the first access will not be reflected.

        Returns:
            The skill content string.
        """
        if self._cached_content is not None:
            return self._cached_content
        resources_block = _build_available_resources_block(self._resources)
        scripts_block = _build_available_scripts_block(self._scripts)
        self._cached_content = f"{self._content}\n\n{resources_block}\n\n{scripts_block}"
        return self._cached_content

    async def get_resource(self, name: str) -> SkillResource | None:
        """Get a resource by name.

        Args:
            name: The resource name to look up (case-insensitive).

        Returns:
            The :class:`SkillResource`, or ``None`` when no resource with the
            given name exists.
        """
        name_lower = name.lower()
        return next((r for r in self._resources if r.name.lower() == name_lower), None)

    async def get_script(self, name: str) -> SkillScript | None:
        """Get a script by name.

        Args:
            name: The script name to look up (case-insensitive).

        Returns:
            The :class:`SkillScript`, or ``None`` when no script with the
            given name exists.
        """
        name_lower = name.lower()
        return next((s for s in self._scripts if s.name.lower() == name_lower), None)


# endregion

# region Script Runners


@runtime_checkable
class SkillScriptRunner(Protocol):
    """Protocol for skill script runners.

    A script runner determines how **file-based** skill scripts are
    run. Implementations decide the execution strategy
    (e.g., local subprocess, hosted code execution environment,
    user-provided callable).

    Code-defined scripts (registered via the ``@skill.script`` decorator)
    are always executed **in-process** and do not use a script runner.

    Any callable (sync or async) matching the ``__call__`` signature
    satisfies this protocol.
    """

    def __call__(
        self, skill: FileSkill, script: FileSkillScript, args: dict[str, Any] | list[str] | None = None
    ) -> Any:
        """Run a skill script.

        The :class:`SkillsProvider` resolves skill and script names
        before calling this method, so implementations receive fully
        resolved objects.

        Args:
            skill: The file-based skill that owns the script.
            script: The file-based script to run.
            args: Optional arguments for the script.

        Returns:
            The result. May be any type; the framework
            serialises it automatically via
            :meth:`~FunctionTool.parse_result`.
        """
        ...


# endregion

SKILL_FILE_NAME: Final[str] = "SKILL.md"
# How deep to search for SKILL.md files within the top-level skill_paths directories.
# This is separate from DEFAULT_SEARCH_DEPTH which controls per-skill resource/script scanning.
MAX_SEARCH_DEPTH: Final[int] = 2
MAX_NAME_LENGTH: Final[int] = 64
MAX_DESCRIPTION_LENGTH: Final[int] = 1024
MAX_COMPATIBILITY_LENGTH: Final[int] = 500
DEFAULT_RESOURCE_EXTENSIONS: Final[tuple[str, ...]] = (
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".xml",
    ".txt",
)
DEFAULT_SCRIPT_EXTENSIONS: Final[tuple[str, ...]] = (".py",)
# How deep to scan for resource/script files within each individual skill directory.
# This is separate from MAX_SEARCH_DEPTH which controls SKILL.md discovery.
DEFAULT_SEARCH_DEPTH: Final[int] = 2


# region Patterns and prompt template

# Matches YAML frontmatter delimited by "---" lines.
# The \uFEFF? prefix allows an optional UTF-8 BOM.
FRONTMATTER_RE = re.compile(
    r"\A\uFEFF?---\s*$(.+?)^---\s*$",
    re.MULTILINE | re.DOTALL,
)

# Matches top-level YAML "key: value" lines (unindented). Group 1 = key,
# Group 2 = quoted value, Group 3 = unquoted value. Only matches keys at
# column 0 so that indented children (e.g. under "metadata:") are not
# mistakenly captured as top-level fields.
YAML_KV_RE = re.compile(
    r"^([\w-]+)\s*:\s*(?:[\"'](.+?)[\"']|(.+?))\s*$",
    re.MULTILINE,
)

# Matches a YAML "metadata:" block followed by indented key-value pairs.
YAML_METADATA_BLOCK_RE = re.compile(
    r"^metadata\s*:\s*$\n((?:[ \t]+\S.*\n?)+)",
    re.MULTILINE,
)

# Matches indented "key: value" lines within a metadata block.
YAML_INDENTED_KV_RE = re.compile(
    r"^\s+([\w-]+)\s*:\s*(?:[\"'](.+?)[\"']|(.+?))\s*$",
    re.MULTILINE,
)

# Validates skill names: lowercase letters, numbers, hyphens only;
# must not start or end with a hyphen, and must not contain consecutive hyphens.
VALID_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9]*-[a-z0-9])*[a-z0-9]*$")

# Block scalar indicator characters recognised by the lightweight YAML parser.
_BLOCK_SCALAR_INDICATORS = ("|", ">")


def _parse_yaml_scalar_value(yaml_content: str, kv_match: re.Match[str]) -> str:
    """Resolve the scalar value for an unquoted YAML key-value match.

    If the captured value starts with a YAML block scalar indicator (``|`` or
    ``>``), the function reads subsequent indented continuation lines, strips
    the common leading indentation, and joins them according to the scalar
    style (literal preserves newlines, folded replaces them with spaces).

    Chomping indicators are respected per YAML 1.2 §8.1.1.2:

    * ``-`` (strip) — final line break and trailing empty lines excluded
    * ``+`` (keep) — final line break and any trailing empty lines preserved
    * default (clip) — final line break preserved, trailing empty lines excluded

    For plain (non-block-scalar) values the captured text is returned as-is.
    Note: explicit indentation indicators (e.g. ``|2``) are not supported;
    indentation is auto-detected from the common leading whitespace.
    """
    value: str = kv_match.group(3)

    if not value or value[0] not in _BLOCK_SCALAR_INDICATORS:
        return value

    scalar_style = value[0]
    keep_trailing_newline = len(value) > 1 and value[1] == "+"
    strip_trailing_newline = len(value) > 1 and value[1] == "-"

    # Find the start of the next line after this key-value match.
    next_line_start = yaml_content.find("\n", kv_match.end())
    if next_line_start < 0:
        return value
    next_line_start += 1  # skip the newline character itself

    # Collect indented continuation lines (or blank lines within the block).
    block_lines: list[str] = []
    pos = next_line_start
    while pos < len(yaml_content):
        line_end = yaml_content.find("\n", pos)
        if line_end < 0:
            line = yaml_content[pos:]
            line_end = len(yaml_content)
        else:
            line = yaml_content[pos:line_end]

        if not line or line.isspace():
            # Blank / whitespace-only lines are part of the block.
            block_lines.append("")
            pos = line_end + 1 if line_end < len(yaml_content) else line_end
            continue

        if line[0] not in (" ", "\t"):
            # Non-indented, non-blank line — end of the block.
            break

        block_lines.append(line)
        pos = line_end + 1 if line_end < len(yaml_content) else line_end

    # Strip trailing blank lines collected from the block.
    while block_lines and block_lines[-1] == "":
        block_lines.pop()

    if not block_lines:
        return ""

    # Determine the common leading indentation across non-empty lines.
    # Only space/tab characters count as indentation (matches YAML semantics).
    def _indent_width(s: str) -> int:
        i = 0
        while i < len(s) and s[i] in (" ", "\t"):
            i += 1
        return i

    common_indent = min(_indent_width(line) for line in block_lines if line)
    normalized = [line[common_indent:] if line else "" for line in block_lines]

    # Literal preserves newlines; folded joins non-empty lines with spaces.
    parsed = "\n".join(normalized) if scalar_style == "|" else " ".join(line for line in normalized if line)

    if keep_trailing_newline:
        return parsed + "\n"
    if strip_trailing_newline:
        return parsed
    # Clip (default): literal gets a trailing newline, folded does not.
    if scalar_style == "|":
        return parsed + "\n"
    return parsed


# Default system prompt template for advertising available skills to the model.
# Use {skills} as the placeholder for the generated skills XML list.
DEFAULT_SKILLS_INSTRUCTION_PROMPT = """\
You have access to skills containing domain-specific knowledge and capabilities.
Each skill provides specialized instructions, reference documents, and assets for specific tasks.

<available_skills>
{skills}
</available_skills>

When a task aligns with a skill's domain, follow these steps in exact order:
- Use `load_skill` to retrieve the skill's instructions.
- Follow the provided guidance.
{resource_instructions}
{runner_instructions}
Only load what is needed, when it is needed."""

RESOURCE_INSTRUCTIONS: Final[str] = (
    "- Use `read_skill_resource` to read any referenced resources, using the name exactly as listed\n"
    '   (e.g. `"style-guide"` not `"style-guide.md"`, `"references/FAQ.md"` not `"FAQ.md"`).\n'
)

SCRIPT_RUNNER_INSTRUCTIONS: Final[str] = (
    "- Use `run_skill_script` to run referenced scripts, using the name exactly as listed.\n"
    "- Pass script arguments inside `args` as a JSON object"
    ' (e.g. `args: {"length": 24}`), not as top-level tool parameters.\n'
)

# endregion

# region SkillsProvider

_TSkillsProvider = TypeVar("_TSkillsProvider", bound="SkillsProvider")


class SkillsProvider(ContextProvider):
    """Context provider that advertises skills and exposes skill tools.

    Accepts a :class:`SkillsSource`, a single :class:`Skill`, or a
    sequence of :class:`Skill` instances. For file-based skills, use
    :meth:`from_paths`. For advanced multi-source scenarios, compose
    sources directly (e.g. :class:`AggregatingSkillsSource`,
    :class:`FilteringSkillsSource`, :class:`DeduplicatingSkillsSource`).

    Follows the progressive-disclosure pattern from the
    `Agent Skills specification <https://agentskills.io/>`_:

    1. **Advertise** — injects skill names and descriptions into the system
       prompt (~100 tokens per skill).
    2. **Load** — returns the full skill body via ``load_skill``.
    3. **Read resources** — returns supplementary content via
       ``read_skill_resource``.

    **Security:** file-based metadata is XML-escaped before prompt injection,
    and file-based resource reads are guarded against path traversal and
    symlink escape.  Only use skills from trusted sources.

    **Security considerations (external skill sources):** which skills are
    available, and how much trust to place in them, is entirely determined by
    the :class:`SkillsSource` instances this provider is configured with — see
    :class:`SkillsSource` for source-level trust-boundary guidance (this
    includes external sources such as skills discovered over MCP via
    :class:`MCPSkillsSource`). Skill content (names, descriptions, and full
    bodies loaded via ``load_skill``) is injected into the agent's context
    as-is, so a compromised or adversarial source can attempt indirect prompt
    injection, and the ``run_skill_script`` tool executes scripts supplied by
    the source. Only enable script-capable or external sources you trust.

    **Tool approval:** by default every tool exposed by this provider
    (``load_skill``, ``read_skill_resource``, and ``run_skill_script``) is
    registered with ``approval_mode="always_require"``, so each skill operation
    needs approval.  To run unattended, pass one of the static
    auto-approval rules to :class:`~agent_framework.ToolApprovalMiddleware` (via
    ``auto_approval_rules``):
    :meth:`read_only_tools_auto_approval_rule` approves only the read-only tools
    (``load_skill`` and ``read_skill_resource``) while still prompting for
    ``run_skill_script``, and :meth:`all_tools_auto_approval_rule` approves every
    skill tool including script execution.  Alternatively, for trusted skills,
    set ``disable_load_skill_approval``, ``disable_read_skill_resource_approval``,
    and/or ``disable_run_skill_script_approval`` to opt individual tools out of
    approval entirely (those tools are registered with
    ``approval_mode="never_require"`` and are not surfaced as approval requests;
    the auto-approval rules only apply to tools that still require approval).

    Examples:
        File-based factory (recommended for single-source file skills):

        .. code-block:: python

            provider = SkillsProvider.from_paths("./skills", script_runner=my_runner)

        Code-defined skills:

        .. code-block:: python

            my_skill = InlineSkill(
                name="my-skill",
                description="Example skill",
                instructions="Use this skill for ...",
            )
            provider = SkillsProvider([my_skill])

        Composing multiple sources with filtering and deduplication:

        .. code-block:: python

            source = DeduplicatingSkillsSource(
                FilteringSkillsSource(
                    AggregatingSkillsSource([
                        FileSkillsSource("./skills", script_runner=my_runner),
                        InMemorySkillsSource([my_code_skill]),
                    ]),
                    predicate=lambda s: s.frontmatter.name != "internal",
                )
            )
            provider = SkillsProvider(source)

    .. note::

        By default, skills are cached after first load.  Set
        ``disable_caching=True`` to re-query the source on every agent
        run, so that updates to file-based skills or code-defined skill
        lists are always picked up while filtering and deduplication
        remain in effect.

    Attributes:
        DEFAULT_SOURCE_ID: Default value for the ``source_id`` used by this provider.
        LOAD_SKILL_TOOL_NAME: Name of the tool that loads a skill.
        READ_SKILL_RESOURCE_TOOL_NAME: Name of the tool that reads a skill resource.
        RUN_SKILL_SCRIPT_TOOL_NAME: Name of the tool that runs a skill script.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "agent_skills"

    #: Name of the tool that loads the full content of a skill.
    LOAD_SKILL_TOOL_NAME: ClassVar[str] = "load_skill"
    #: Name of the tool that reads a resource associated with a skill.
    READ_SKILL_RESOURCE_TOOL_NAME: ClassVar[str] = "read_skill_resource"
    #: Name of the tool that runs a script associated with a skill.
    RUN_SKILL_SCRIPT_TOOL_NAME: ClassVar[str] = "run_skill_script"

    #: Names of the tools that only read (never execute scripts from) the skills source.
    _READ_ONLY_TOOL_NAMES: ClassVar[frozenset[str]] = frozenset({
        LOAD_SKILL_TOOL_NAME,
        READ_SKILL_RESOURCE_TOOL_NAME,
    })

    #: Names of all tools exposed by this provider.
    _ALL_TOOL_NAMES: ClassVar[frozenset[str]] = frozenset({
        LOAD_SKILL_TOOL_NAME,
        READ_SKILL_RESOURCE_TOOL_NAME,
        RUN_SKILL_SCRIPT_TOOL_NAME,
    })

    @staticmethod
    def _is_local_tool_call(function_call: Content) -> bool:
        """Return whether a function call targets this provider's local tools.

        Hosted-tool calls carry a ``server_label`` in their
        ``additional_properties`` and are a separate server-scoped approval
        boundary that must be passed through untouched (see
        :func:`agent_framework._tools._is_hosted_tool_approval`). These rules
        only ever auto-approve the provider's own local tools, so any call that
        carries a ``server_label`` is rejected even if its name collides with a
        skill tool name.
        """
        return not function_call.additional_properties.get("server_label")

    @staticmethod
    def read_only_tools_auto_approval_rule(function_call: Content) -> bool:
        """Auto-approval rule that approves only the read-only skill tools.

        By default the tools exposed by :class:`SkillsProvider` require
        approval. This rule only applies to tools that still require approval;
        tools opted out via the ``disable_*_approval`` constructor arguments run
        without approval regardless.
        Pass this rule to :class:`~agent_framework.ToolApprovalMiddleware` (via
        ``auto_approval_rules``) to automatically approve the tools that read
        skill content (``load_skill`` and ``read_skill_resource``), while still
        prompting for script execution (``run_skill_script``).

        Hosted-tool calls (those carrying a ``server_label``) are never
        auto-approved, even when their name matches a skill tool, so the rule
        stays scoped to this provider's local tools.

        .. warning::
            **Security — avoid tool-name collisions.** This rule approves local
            tool calls by tool name only (``load_skill`` and
            ``read_skill_resource``). Any other local tool registered under one
            of these names — for example a tool with a caller-configurable name
            such as the shell tool — may also be auto-approved, bypassing the
            human approval boundary. Ensure no other tool collides with these
            reserved names.

        Args:
            function_call: The pending ``function_call`` content.

        Returns:
            ``True`` for read-only skill tools, ``False`` otherwise so that
            subsequent rules continue to be evaluated.
        """
        return (
            SkillsProvider._is_local_tool_call(function_call)
            and function_call.name in SkillsProvider._READ_ONLY_TOOL_NAMES
        )

    @staticmethod
    def all_tools_auto_approval_rule(function_call: Content) -> bool:
        """Auto-approval rule that approves every skill tool.

        By default the tools exposed by :class:`SkillsProvider` require
        approval. This rule only applies to tools that still require approval;
        tools opted out via the ``disable_*_approval`` constructor arguments run
        without approval regardless.
        Pass this rule to :class:`~agent_framework.ToolApprovalMiddleware` (via
        ``auto_approval_rules``) to automatically approve every skill tool,
        including the script execution tool (``run_skill_script``).

        Hosted-tool calls (those carrying a ``server_label``) are never
        auto-approved, even when their name matches a skill tool, so the rule
        stays scoped to this provider's local tools.

        .. warning::
            **Security — avoid tool-name collisions.** This rule approves local
            tool calls by tool name only (``load_skill``,
            ``read_skill_resource``, and ``run_skill_script``). Any other local
            tool registered under one of these names — for example a tool with a
            caller-configurable name such as the shell tool — may also be
            auto-approved, bypassing the human approval boundary. Ensure no other
            tool collides with these reserved names.

        Args:
            function_call: The pending ``function_call`` content.

        Returns:
            ``True`` for any skill tool, ``False`` otherwise so that subsequent
            rules continue to be evaluated.
        """
        return (
            SkillsProvider._is_local_tool_call(function_call) and function_call.name in SkillsProvider._ALL_TOOL_NAMES
        )

    def __init__(
        self,
        source: SkillsSource | Sequence[Skill] | Skill,
        *,
        instruction_template: str | None = None,
        disable_caching: bool = False,
        cache_refresh_interval: timedelta | None = None,
        disable_load_skill_approval: bool = False,
        disable_read_skill_resource_approval: bool = False,
        disable_run_skill_script_approval: bool = False,
        source_id: str | None = None,
    ) -> None:
        """Initialize a SkillsProvider.

        Accepts a :class:`SkillsSource`, a single :class:`Skill`, or a
        sequence of :class:`Skill` instances.  When skills are passed
        directly, they are automatically deduplicated and cached.

        A caller-supplied :class:`SkillsSource` is used as-is: it is **not**
        automatically deduplicated or wrapped in a
        :class:`CachingSkillsSource`. This keeps context-aware sources safe —
        auto-caching a caller source in a single shared cache could replay one
        agent's/tenant's skills for another. Compose
        :class:`DeduplicatingSkillsSource` / :class:`CachingSkillsSource`
        (optionally with a ``cache_isolation_key_selector``) yourself when you
        need them.

        For file-based skills, use :meth:`from_paths` or compose sources
        directly using :class:`FileSkillsSource` and other source classes.

        Args:
            source: A :class:`SkillsSource`, a single :class:`Skill`,
                or a sequence of :class:`Skill` instances.

        Keyword Args:
            instruction_template: Custom system-prompt template for
                advertising skills. Must contain a ``{skills}`` placeholder for the
                generated skills list. May optionally contain
                ``{runner_instructions}`` and/or ``{resource_instructions}``
                placeholders; when present, they are filled with built-in
                guidance for script execution and resource reading respectively.
                When omitted, those instructions are simply not included in the
                rendered prompt (the corresponding tools are still registered).
                Uses a built-in template when ``None``.
            disable_caching: When ``True``, the built-in file/in-memory source
                is not wrapped in a :class:`CachingSkillsSource`, so skills are
                rebuilt on every invocation. This only affects the sources the
                provider builds internally (from a :class:`Skill`, a sequence of
                skills, or :meth:`from_paths`); a caller-supplied
                :class:`SkillsSource` is never auto-cached regardless of this
                flag. Defaults to ``False``.
            cache_refresh_interval: Optional duration after which the built-in
                cache is considered stale and skills are re-discovered on the
                next invocation. Like ``disable_caching``, this only affects the
                :class:`CachingSkillsSource` the provider builds internally
                (from a :class:`Skill` or a sequence of skills); it has no
                effect on a caller-supplied :class:`SkillsSource` (compose your
                own :class:`CachingSkillsSource` with a ``refresh_interval`` for
                those) and is ignored when ``disable_caching=True``. When
                ``None`` (the default), the built-in cache never expires.
            disable_load_skill_approval: When ``True``, the ``load_skill`` tool
                is registered with ``approval_mode="never_require"`` so it runs
                without approval.  Defaults to ``False`` (approval required).
                Only enable this for skills from a trusted source.
            disable_read_skill_resource_approval: When ``True``, the
                ``read_skill_resource`` tool is registered with
                ``approval_mode="never_require"`` so it runs without approval.
                Defaults to ``False`` (approval required).  Only enable this for
                skills from a trusted source.
            disable_run_skill_script_approval: When ``True``, the
                ``run_skill_script`` tool is registered with
                ``approval_mode="never_require"`` so it runs without approval.
                Defaults to ``False`` (approval required).  Only enable this for
                skills and scripts from a trusted source.
            source_id: Unique identifier for this provider instance.

        .. note::

            By default every skill tool requires approval. To approve them
            automatically, pass :meth:`read_only_tools_auto_approval_rule` or
            :meth:`all_tools_auto_approval_rule` to
            :class:`~agent_framework.ToolApprovalMiddleware`. Alternatively, for
            trusted skills, set one or more of
            ``disable_load_skill_approval``, ``disable_read_skill_resource_approval``,
            and ``disable_run_skill_script_approval`` to opt individual tools out
            of approval entirely (the auto-approval rules only apply to tools
            that still require approval). See
            ``samples/02-agents/skills/skills_auto_approval/skills_auto_approval.py``
            for the auto-approval pattern and
            ``samples/02-agents/skills/script_approval/script_approval.py`` for
            the manual approval loop.
        """
        super().__init__(source_id or self.DEFAULT_SOURCE_ID)

        if isinstance(source, (str, Path)):
            raise TypeError(
                f"SkillsProvider does not accept path strings directly. "
                f"Use SkillsProvider.from_paths({source!r}) for file-based skills."
            )

        if isinstance(source, Skill):
            leaf: SkillsSource = InMemorySkillsSource([source])
            source = DeduplicatingSkillsSource(
                leaf if disable_caching else CachingSkillsSource(leaf, refresh_interval=cache_refresh_interval)
            )
        elif isinstance(source, SkillsSource):
            # Caller-supplied source: the caller owns the whole pipeline, so it
            # is used as-is with no automatic caching (or deduplication).
            # Auto-wrapping a caller source in a single shared, unkeyed
            # CachingSkillsSource would be unsafe: if the source is
            # context-aware (e.g. filters skills per agent/tenant via the
            # SkillsSourceContext), the first invocation's skills would be
            # cached and replayed for every later context, leaking skills
            # across agents/tenants. Callers who want caching should compose
            # CachingSkillsSource themselves (optionally with a
            # cache_isolation_key_selector). Only the built-in, context-
            # independent leaf sources above/below are auto-cached.
            pass
        else:
            leaf = InMemorySkillsSource(list(source))
            source = DeduplicatingSkillsSource(
                leaf if disable_caching else CachingSkillsSource(leaf, refresh_interval=cache_refresh_interval)
            )

        self._source = source
        self._instruction_template = instruction_template
        self._disable_caching = disable_caching
        self._cache_refresh_interval = cache_refresh_interval
        self._disable_load_skill_approval = disable_load_skill_approval
        self._disable_read_skill_resource_approval = disable_read_skill_resource_approval
        self._disable_run_skill_script_approval = disable_run_skill_script_approval

    @classmethod
    def from_paths(
        cls: type[_TSkillsProvider],
        skill_paths: str | Path | Sequence[str | Path],
        *,
        script_runner: SkillScriptRunner | None = None,
        resource_extensions: tuple[str, ...] | None = None,
        script_extensions: tuple[str, ...] | None = None,
        search_depth: int = DEFAULT_SEARCH_DEPTH,
        script_filter: Callable[[str, str], bool] | None = None,
        resource_filter: Callable[[str, str], bool] | None = None,
        instruction_template: str | None = None,
        disable_caching: bool = False,
        cache_refresh_interval: timedelta | None = None,
        disable_load_skill_approval: bool = False,
        disable_read_skill_resource_approval: bool = False,
        disable_run_skill_script_approval: bool = False,
        source_id: str | None = None,
    ) -> _TSkillsProvider:
        """Create a provider from one or more file-based skill directories.

        Discovers skills from ``SKILL.md`` files in the given directories,
        deduplicates them, and creates the provider.

        Args:
            skill_paths: One or more directory paths to search for
                file-based skills.

        Keyword Args:
            script_runner: Strategy for running file-based skill scripts.
                When ``None``, file-based scripts are not executable.
            resource_extensions: File extensions recognized as discoverable
                resources.  Defaults to
                ``(".md", ".json", ".yaml", ".yml", ".csv", ".xml", ".txt")``.
            script_extensions: File extensions recognized as discoverable
                scripts.  Defaults to ``(".py",)``.
            search_depth: Maximum depth to search for script and resource
                files within each skill directory.  A value of ``1`` searches
                only the skill root; ``2`` (the default) searches the root
                plus one level of subdirectories.  Must be >= 1.
            script_filter: Optional predicate ``(skill_name, relative_file_path) -> bool``
                that filters discovered script files.  Returns ``True`` to
                include or ``False`` to exclude.  When ``None``, all scripts
                matching allowed extensions are included.
            resource_filter: Optional predicate ``(skill_name, relative_file_path) -> bool``
                that filters discovered resource files.  Returns ``True`` to
                include or ``False`` to exclude.  When ``None``, all resources
                matching allowed extensions are included.
            instruction_template: Custom system-prompt template for
                advertising skills.  Must contain a ``{skills}`` placeholder.
                Uses a built-in template when ``None``.
            disable_caching: When ``True``, the file-discovery source is not
                wrapped in a :class:`CachingSkillsSource`, so skills are
                re-discovered on every invocation. Defaults to ``False``.
            cache_refresh_interval: Optional duration after which the file-
                discovery cache is considered stale and skills are re-discovered
                on the next invocation. When ``None`` (the default) the cache
                never expires; ignored when ``disable_caching=True``.
            disable_load_skill_approval: When ``True``, the ``load_skill`` tool
                runs without approval.  Defaults to ``False``.  Only enable this
                for skills from a trusted source.
            disable_read_skill_resource_approval: When ``True``, the
                ``read_skill_resource`` tool runs without approval.  Defaults to
                ``False``.  Only enable this for skills from a trusted source.
            disable_run_skill_script_approval: When ``True``, the
                ``run_skill_script`` tool runs without approval.  Defaults to
                ``False``.  Only enable this for skills and scripts from a
                trusted source.
            source_id: Unique identifier for this provider instance.

        Returns:
            A configured :class:`SkillsProvider`.

        .. note::

            By default every skill tool requires approval. To approve them
            automatically, pass :meth:`read_only_tools_auto_approval_rule` or
            :meth:`all_tools_auto_approval_rule` to
            :class:`~agent_framework.ToolApprovalMiddleware`. Alternatively, for
            trusted skills, set one or more of ``disable_load_skill_approval``,
            ``disable_read_skill_resource_approval``, and
            ``disable_run_skill_script_approval`` to opt individual tools out of
            approval entirely.
        """
        file_source: SkillsSource = FileSkillsSource(
            skill_paths,
            script_runner=script_runner,
            resource_extensions=resource_extensions,
            script_extensions=script_extensions,
            search_depth=search_depth,
            script_filter=script_filter,
            resource_filter=resource_filter,
        )
        # Cache the (potentially expensive) file-discovery leaf directly, then
        # deduplicate. The composed pipeline is handed to __init__ as a
        # caller-supplied source, which is intentionally left un-wrapped, so
        # caching is applied here. The file source is context-independent, so a
        # single shared cache is safe.
        source = DeduplicatingSkillsSource(
            file_source
            if disable_caching
            else CachingSkillsSource(file_source, refresh_interval=cache_refresh_interval)
        )
        # Only forward the approval-disable kwargs when explicitly enabled, so a
        # subclass with the previous __init__ signature keeps working.
        forwarded_kwargs: dict[str, Any] = {}
        if disable_load_skill_approval:
            forwarded_kwargs["disable_load_skill_approval"] = True
        if disable_read_skill_resource_approval:
            forwarded_kwargs["disable_read_skill_resource_approval"] = True
        if disable_run_skill_script_approval:
            forwarded_kwargs["disable_run_skill_script_approval"] = True
        return cls(
            source,
            instruction_template=instruction_template,
            disable_caching=disable_caching,
            source_id=source_id,
            **forwarded_kwargs,
        )

    @staticmethod
    def _create_instructions(
        prompt_template: str | None,
        skills: Sequence[Skill],
    ) -> str | None:
        """Create the system-prompt text that advertises available skills.

        Generates an XML list of ``<skill>`` elements (sorted by name) and
        inserts it into *prompt_template* at the ``{skills}`` placeholder.
        Script-runner instructions are inserted at the
        ``{runner_instructions}`` placeholder and resource-reading
        instructions at the ``{resource_instructions}`` placeholder.

        Args:
            prompt_template: Custom template string with ``{skills}`` and
                optional ``{runner_instructions}`` and ``{resource_instructions}``
                placeholders, or ``None`` to use the built-in default.
            skills: Registered skills.

        Returns:
            The formatted instruction string, or ``None`` when *skills* is empty.

        Raises:
            ValueError: If *prompt_template* is not a valid format string
                (e.g. missing ``{skills}`` placeholder).
        """
        runner_instructions = SCRIPT_RUNNER_INSTRUCTIONS
        resource_instructions = RESOURCE_INSTRUCTIONS
        template = DEFAULT_SKILLS_INSTRUCTION_PROMPT

        if prompt_template is not None:
            # Validate that the custom template contains a valid {skills} placeholder
            try:
                result = prompt_template.format(
                    skills="__PROBE__",
                    runner_instructions="__EXEC_PROBE__",
                    resource_instructions="__RES_PROBE__",
                )
            except (KeyError, IndexError, ValueError) as exc:
                raise ValueError(
                    "The provided instruction_template is not a valid format string. "
                    "It must contain a '{skills}' placeholder and escape any literal"  # ruff:ignore[missing-f-string-syntax]
                    " '{' or '}' "
                    "by doubling them ('{{' or '}}')."
                ) from exc
            if "__PROBE__" not in result:
                raise ValueError(
                    "The provided instruction_template must contain a '{skills}' placeholder."  # ruff:ignore[missing-f-string-syntax]
                )
            template = prompt_template

        if not skills:
            return None

        lines: list[str] = []
        # Sort by name for deterministic output
        for skill in sorted(skills, key=lambda s: s.frontmatter.name):
            lines.append("  <skill>")
            lines.append(f"    <name>{xml_escape(skill.frontmatter.name)}</name>")
            lines.append(f"    <description>{xml_escape(skill.frontmatter.description)}</description>")
            lines.append("  </skill>")

        return template.format(
            skills="\n".join(lines),
            runner_instructions=runner_instructions or "",
            resource_instructions=resource_instructions or "",
        )

    async def _create_context(
        self, source_context: SkillsSourceContext
    ) -> tuple[Sequence[Skill], str | None, list[FunctionTool]]:
        """Build skills, instructions, and tools from the source.

        Queries the source for skills and constructs the instruction prompt
        and tool definitions.  Caching of the skills list is handled by the
        source pipeline (see :class:`CachingSkillsSource`), so this method
        rebuilds instructions and tools from the (possibly cached) skills on
        every call.

        Args:
            source_context: Contextual information about the agent and session
                requesting skills, forwarded to the source pipeline.

        Returns:
            A tuple of ``(skills, instructions, tools)``.
        """
        skills = await self._source.get_skills(source_context)

        if not skills:
            return skills, None, []

        instructions = self._create_instructions(
            prompt_template=self._instruction_template,
            skills=skills,
        )

        tools = self._create_tools(skills=skills)

        return skills, instructions, tools

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject skill instructions and tools into the session context.

        Called by the framework before the agent runs.  Loads skills from the
        configured source (built-in file/in-memory sources are cached by the
        source pipeline unless ``disable_caching=True``; a caller-supplied
        source is queried as its own pipeline dictates) and builds the
        instruction prompt and tool definitions.  When at least one skill is
        registered, appends the skill-list system prompt and the ``load_skill``
        / ``read_skill_resource`` tools to *context*.

        When any registered skill defines one or more scripts (file-based or
        code-based), the system prompt also includes script-runner
        instructions (embedded via the ``{runner_instructions}`` placeholder),
        and the ``run_skill_script`` tool is included alongside the base tools.

        Args:
            agent: The agent instance about to run.
            session: The current agent session.
            context: Session context to extend with instructions and tools.
            state: Mutable per-run state dictionary (unused by this provider).
        """
        mark_feature_used(FeatureIndex.CORE_SKILLS_PROVIDER)
        source_context = SkillsSourceContext(agent=agent, session=session)
        skills, instructions, tools = await self._create_context(source_context)

        if not skills:
            return

        context.extend_instructions(self.source_id, instructions)  # type: ignore[arg-type]
        context.extend_tools(self.source_id, tools)

    @staticmethod
    def _approval_mode(approval_disabled: bool) -> ApprovalMode:
        """Return the ``approval_mode`` for a tool given its disable flag.

        Args:
            approval_disabled: When ``True``, the tool runs without approval.

        Returns:
            ``"never_require"`` when approval is disabled, otherwise
            ``"always_require"``.
        """
        return "never_require" if approval_disabled else "always_require"

    def _create_tools(
        self,
        skills: Sequence[Skill],
    ) -> list[FunctionTool]:
        """Create the tool definitions for skill interaction.

        Always includes ``load_skill``, ``read_skill_resource``, and
        ``run_skill_script``.  By default every tool is registered with
        ``approval_mode="always_require"`` so each skill operation needs
        approval; use :meth:`read_only_tools_auto_approval_rule` or
        :meth:`all_tools_auto_approval_rule` with
        :class:`~agent_framework.ToolApprovalMiddleware` to approve them
        automatically.  For trusted skills, individual tools can be opted out of
        approval entirely via the ``disable_load_skill_approval``,
        ``disable_read_skill_resource_approval``, and
        ``disable_run_skill_script_approval`` constructor arguments, in which
        case the corresponding tool is registered with
        ``approval_mode="never_require"``.

        Args:
            skills: The skills to bind to tool handlers.

        Returns:
            A list of :class:`FunctionTool` instances.
        """

        async def _load(skill_name: str) -> str:
            return await self._load_skill(skills, skill_name)

        async def _read_resource(skill_name: str, resource_name: str, **kwargs: Any) -> Any:
            return await self._read_skill_resource(skills, skill_name, resource_name, **kwargs)

        async def _run_script(
            skill_name: str, script_name: str, args: dict[str, Any] | list[str] | None = None, **kwargs: Any
        ) -> Any:
            return await self._run_skill_script(skills, skill_name, script_name, args, **kwargs)

        return [
            FunctionTool(
                name=self.LOAD_SKILL_TOOL_NAME,
                description="Loads the full instructions for a specific skill.",
                func=_load,
                approval_mode=self._approval_mode(self._disable_load_skill_approval),
                input_model={
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string", "description": "The name of the skill to load."},
                    },
                    "required": ["skill_name"],
                },
            ),
            FunctionTool(
                name=self.READ_SKILL_RESOURCE_TOOL_NAME,
                description=("Reads a resource associated with a skill, such as references, assets, or dynamic data."),
                func=_read_resource,
                approval_mode=self._approval_mode(self._disable_read_skill_resource_approval),
                input_model={
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string", "description": "The name of the skill."},
                        "resource_name": {
                            "type": "string",
                            "description": "The name of the resource.",
                        },
                    },
                    "required": ["skill_name", "resource_name"],
                },
            ),
            FunctionTool(
                name=self.RUN_SKILL_SCRIPT_TOOL_NAME,
                description="Runs a script associated with a skill.",
                func=_run_script,
                approval_mode=self._approval_mode(self._disable_run_skill_script_approval),
                input_model={
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string", "description": "The name of the skill."},
                        "script_name": {
                            "type": "string",
                            "description": (
                                "The name of the script to run as listed in the skill, "
                                "preserving any directory prefix exactly as shown. "
                                "Do not add or remove path prefixes."
                            ),
                        },
                        "args": {
                            "oneOf": [
                                {
                                    "type": "object",
                                    "additionalProperties": True,
                                    "description": (
                                        'Named arguments as key-value pairs (e.g. {"length": 24, "uppercase": true}).'
                                    ),
                                },
                                {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": (
                                        "Positional CLI arguments as a string array "
                                        '(e.g. ["input.docx", "--output", "result.idx"]).'
                                    ),
                                },
                                {"type": "null"},
                            ],
                            "default": None,
                            "description": (
                                "Arguments to pass to the script. "
                                "Use an array of strings for CLI-style positional arguments "
                                '(e.g. ["input.docx", "--output", "result.idx"]), '
                                "or an object for named parameters "
                                '(e.g. {"length": 24, "uppercase": true}). '
                                "How these values are mapped to the underlying script "
                                "is determined by the script implementation or configured runner."
                            ),
                        },
                    },
                    "required": ["skill_name", "script_name"],
                },
            ),
        ]

    @staticmethod
    def _find_skill(skills: Sequence[Skill], name: str) -> Skill | None:
        """Find a skill by name (case-insensitive linear scan)."""
        name_lower = name.lower()
        return next((s for s in skills if s.frontmatter.name.lower() == name_lower), None)

    async def _load_skill(self, skills: Sequence[Skill], skill_name: str) -> str:
        """Return the full content for the named skill.

        Delegates to the skill's :meth:`~Skill.get_content` method, which
        handles format differences between file-based and code-defined skills.

        Args:
            skills: The skills to look up the skill from.
            skill_name: The name of the skill to load.

        Returns:
            The skill content text, or a user-facing error message if
            *skill_name* is empty or not found.
        """
        if not skill_name or not skill_name.strip():
            return "Error: Skill name cannot be empty."

        skill = self._find_skill(skills, skill_name)
        if skill is None:
            return f"Error: Skill '{skill_name}' not found."

        logger.info("Loading skill: %s", skill_name)

        return await skill.get_content()

    async def _run_skill_script(
        self,
        skills: Sequence[Skill],
        skill_name: str,
        script_name: str,
        args: dict[str, Any] | list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run a named script from a skill.

        Resolves the skill and script by name, then delegates execution
        to :meth:`SkillScript.run`.

        Args:
            skills: The skills to look up the skill from.
            skill_name: The name of the owning skill.
            script_name: The script name to look up (case-insensitive).
            args: Optional arguments for the script, provided by the
                agent/LLM.
            **kwargs: Runtime keyword arguments forwarded only to script
                functions that accept ``**kwargs`` (e.g. arguments passed via
                ``agent.run(user_id="123")``).

        Returns:
            The script result. Returns a user-facing error string for
            validation failures (empty or unknown skill/script name).

        Raises:
            Exception: Re-raises any exception raised while running the script,
                delegating error handling to the function-invocation pipeline
                (which applies its own ``include_detailed_errors`` policy).
        """
        if not skill_name or not skill_name.strip():
            return "Error: Skill name cannot be empty."

        if not script_name or not script_name.strip():
            return "Error: Script name cannot be empty."

        skill = self._find_skill(skills, skill_name)
        if not skill:
            return f"Error: Skill '{skill_name}' not found."

        script = await skill.get_script(script_name)
        if not script:
            return f"Error: Script '{script_name}' not found in skill '{skill_name}'."

        try:
            return await script.run(skill, args, **kwargs)
        except Exception:
            logger.exception("Error running script '%s' in skill '%s'", script_name, skill_name)
            raise

    async def _read_skill_resource(
        self, skills: Sequence[Skill], skill_name: str, resource_name: str, **kwargs: Any
    ) -> Any:
        """Read a named resource from a skill.

        Resolves the resource by case-insensitive name lookup.  Static
        ``content`` is returned directly; callable resources are invoked
        (awaited if async).

        Args:
            skills: The skills to look up the skill from.
            skill_name: The name of the owning skill.
            resource_name: The resource name to look up (case-insensitive).
            **kwargs: Runtime keyword arguments forwarded to resource functions
                that accept ``**kwargs`` (e.g. arguments passed via
                ``agent.run(user_id="123")``).

        Returns:
            The resource content (any type). Returns a user-facing error
            string for validation failures (empty or unknown skill/resource
            name).

        Raises:
            Exception: Re-raises any exception raised while reading the
                resource. Resources take no model-supplied arguments, so a
                swallowed generic error is not actionable by the model;
                re-raising lets the function-invocation pipeline decide how to
                surface it.
        """
        if not skill_name or not skill_name.strip():
            return "Error: Skill name cannot be empty."

        if not resource_name or not resource_name.strip():
            return "Error: Resource name cannot be empty."

        skill = self._find_skill(skills, skill_name)
        if skill is None:
            return f"Error: Skill '{skill_name}' not found."

        resource = await skill.get_resource(resource_name)
        if resource is None:
            return f"Error: Resource '{resource_name}' not found in skill '{skill_name}'."

        try:
            return await resource.read(**kwargs)
        except Exception:
            logger.exception("Failed to read resource '%s' from skill '%s'", resource_name, skill_name)
            raise


# endregion


def _create_script_element(script: SkillScript) -> str:
    """Create an XML ``<script …>`` element from a :class:`SkillScript`.

    When the script has a ``parameters_schema``, the element includes a
    ``<parameters_schema>`` child element containing the JSON schema.
    Otherwise the element is self-closing.

    Args:
        script: The script to create the element from.

    Returns:
        An indented XML element string with ``name``, optional
        ``description`` attributes, and an optional
        ``<parameters_schema>`` child element.
    """
    attrs = f'name="{xml_escape(script.name, quote=True)}"'
    if script.description:
        attrs += f' description="{xml_escape(script.description, quote=True)}"'
    if script.parameters_schema:
        params_json = xml_escape(json.dumps(script.parameters_schema), quote=False)
        return f"  <script {attrs}>\n    <parameters_schema>{params_json}</parameters_schema>\n  </script>"
    return f"  <script {attrs}/>"


# region Skill Sources


@dataclass(frozen=True)
class SkillsSourceContext:
    """Contextual information passed to a :class:`SkillsSource` when retrieving skills.

    Exposes the invoking *agent* and, when available, the current *session* so
    that skill sources and decorators can make context-aware decisions such as
    per-agent filtering (see :class:`FilteringSkillsSource`) or per-key cache
    isolation (see :class:`CachingSkillsSource`).

    The context is constructed by :class:`SkillsProvider` from the invoking
    agent run and flows through every source and decorator in the pipeline.

    Attributes:
        agent: The agent requesting skills.
        session: The session associated with the agent invocation, if any.
    """

    agent: SupportsAgentRun
    session: AgentSession | None = None


class SkillsSource(ABC):
    """Abstract base class for skill sources.

    A skill source discovers and returns :class:`Skill` instances from a
    particular origin.  The framework calls :meth:`get_skills` to obtain
    the available skills; implementations decide *where* and *how* skills
    are discovered (filesystem, memory, network, etc.).

    Subclass this to create custom skill sources.

    Security considerations:
        A skill source is a trust boundary. The skills it returns — their
        names, descriptions, instructions, and any scripts or resources — are
        injected into the agent's context and tool surface, and may be
        executed (for sources that support script execution). Skills only
        reach the agent when a source is explicitly registered, so this is
        opt-in. Sources that read from a remote or third-party origin (e.g. a
        remote MCP server via :class:`MCPSkillsSource`, a shared filesystem, or
        a database) can be compromised or adversarial, and may return skill
        content designed to manipulate the agent (indirect prompt injection) or
        to exfiltrate data through instructions or scripts the agent is induced
        to run. Only register skill sources for origins you trust, and evaluate
        the content they can return before enabling them in production.
    """

    @abstractmethod
    async def get_skills(self, context: SkillsSourceContext) -> list[Skill]:
        """Discover and return all skills from this source.

        Args:
            context: Contextual information about the agent and session
                requesting skills.

        Returns:
            A list of :class:`Skill` instances discovered by this source.
        """
        ...


class FileSkillsSource(SkillsSource):
    """Skill source that discovers skills from filesystem ``SKILL.md`` files.

    Recursively scans the configured *skill_paths* directories for
    ``SKILL.md`` files (up to 2 levels deep), parses their YAML frontmatter,
    and discovers associated resource and script files by recursively scanning
    each skill directory up to the configured *search_depth*.

    By default, the scan depth is 2 (root + one level of subdirectories).
    Use *script_filter* and *resource_filter* predicates to control which
    discovered files are included.

    Security: file-based metadata is XML-escaped before prompt injection,
    and resource reads are guarded against path traversal and symlink escape.
    Only use skills from trusted sources.

    Examples:
        Basic usage:

        .. code-block:: python

            source = FileSkillsSource(skill_paths="./skills")
            # `context` is normally supplied by SkillsProvider at runtime.
            context = SkillsSourceContext(agent=agent)
            skills = await source.get_skills(context)

        With a script runner and filter predicates:

        .. code-block:: python

            source = FileSkillsSource(
                skill_paths=["./skills", "./more-skills"],
                script_runner=my_runner,
                search_depth=3,
                script_filter=lambda name, path: not path.startswith("tests/"),
            )
    """

    def __init__(
        self,
        skill_paths: str | Path | Sequence[str | Path],
        *,
        script_runner: SkillScriptRunner | None = None,
        resource_extensions: tuple[str, ...] | None = None,
        script_extensions: tuple[str, ...] | None = None,
        search_depth: int = DEFAULT_SEARCH_DEPTH,
        script_filter: Callable[[str, str], bool] | None = None,
        resource_filter: Callable[[str, str], bool] | None = None,
    ) -> None:
        """Initialize a FileSkillsSource.

        Args:
            skill_paths: One or more directory paths to search for file-based
                skills.  Each path may point to an individual skill directory
                (containing ``SKILL.md``) or to a parent that contains skill
                subdirectories.

        Keyword Args:
            script_runner: Strategy for running file-based skill scripts.
                When ``None``, discovered scripts are included but not
                executable (the provider will raise an error if execution
                is attempted without a runner).
            resource_extensions: File extensions recognized as discoverable
                resources.  Defaults to
                ``(".md", ".json", ".yaml", ".yml", ".csv", ".xml", ".txt")``.
            script_extensions: File extensions recognized as discoverable
                scripts.  Defaults to ``(".py",)``.
            search_depth: Maximum depth to search for script and resource
                files within each skill directory.  A value of ``1`` searches
                only the skill root; ``2`` (the default) searches the root
                plus one level of subdirectories.  Must be >= 1.
            script_filter: Optional predicate ``(skill_name, relative_file_path) -> bool``
                that filters discovered script files.  Returns ``True`` to
                include or ``False`` to exclude.  When ``None``, all scripts
                matching allowed extensions are included.
            resource_filter: Optional predicate ``(skill_name, relative_file_path) -> bool``
                that filters discovered resource files.  Returns ``True`` to
                include or ``False`` to exclude.  When ``None``, all resources
                matching allowed extensions are included.

        Raises:
            ValueError: If *search_depth* is less than 1.
        """
        if isinstance(skill_paths, (str, Path)):
            self._skill_paths: list[str] = [str(skill_paths)]
        else:
            self._skill_paths = [str(p) for p in skill_paths]

        self._script_runner = script_runner
        self._resource_extensions = resource_extensions or DEFAULT_RESOURCE_EXTENSIONS
        self._script_extensions = script_extensions or DEFAULT_SCRIPT_EXTENSIONS

        if search_depth < 1:
            raise ValueError(f"search_depth must be >= 1, got {search_depth}")
        self._search_depth: int = search_depth
        self._script_filter = script_filter
        self._resource_filter = resource_filter

    async def get_skills(self, context: SkillsSourceContext) -> list[Skill]:
        """Discover and return all file-based skills from configured paths.

        Scans directories for ``SKILL.md`` files, parses their frontmatter,
        discovers resource and script files, and returns populated
        :class:`Skill` instances.

        Args:
            context: Contextual information about the agent and session
                requesting skills. Accepted for the source contract; this
                source discovers the same skills regardless of context.

        Returns:
            A list of discovered file-based skills.
        """
        mark_feature_used(FeatureIndex.CORE_FILE_SKILLS_SOURCE)
        skills: dict[str, FileSkill] = {}

        discovered = FileSkillsSource._discover_skill_directories(self._skill_paths)
        logger.info("Discovered %d potential skills", len(discovered))

        for skill_path in discovered:
            parsed = FileSkillsSource._read_and_parse_skill_file(skill_path)
            if parsed is None:
                continue

            frontmatter, content = parsed

            if frontmatter.name in skills:
                logger.warning(
                    "Duplicate skill name '%s': skill from '%s' skipped in favor of existing skill",
                    frontmatter.name,
                    skill_path,
                )
                continue

            # Discover file-based resources
            resources: list[SkillResource] = []
            for rn in self._discover_resource_files(skill_path, frontmatter.name):
                resource_full_path = FileSkillsSource._get_validated_resource_path(skill_path, rn)
                resources.append(_FileSkillResource(name=rn, full_path=resource_full_path))

            # Discover file-based scripts
            scripts: list[SkillScript] = []
            for sn in self._discover_script_files(skill_path, frontmatter.name):
                script_full_path = os.path.normpath(os.path.join(skill_path, sn))  # ruff:ignore[blocking-path-method-in-async-function]
                scripts.append(FileSkillScript(name=sn, full_path=script_full_path, runner=self._script_runner))

            file_skill = FileSkill(
                frontmatter=frontmatter,
                content=content,
                path=skill_path,
                resources=resources,
                scripts=scripts,
            )

            skills[file_skill.frontmatter.name] = file_skill
            logger.info("Loaded skill: %s", file_skill.frontmatter.name)

        logger.info("Successfully loaded %d skills", len(skills))
        return list(skills.values())

    @staticmethod
    def _normalize_resource_path(path: str) -> str:
        """Normalize a relative resource path to a canonical forward-slash form.

        Converts backslashes to forward slashes and strips leading ``./``
        prefixes so that ``./refs/doc.md`` and ``refs/doc.md`` resolve
        identically.

        Args:
            path: The relative path to normalize.

        Returns:
            A clean forward-slash-separated path string.
        """
        return PurePosixPath(path.replace("\\", "/")).as_posix()

    @staticmethod
    def _is_path_within_directory(path: str, directory: str) -> bool:
        """Return whether *path* resides under *directory*.

        Comparison uses :meth:`pathlib.Path.is_relative_to`, which respects
        per-platform case-sensitivity rules.

        Args:
            path: Absolute path to check.
            directory: Directory that must be an ancestor of *path*.

        Returns:
            ``True`` if *path* is a descendant of *directory*.
        """
        try:
            return Path(path).is_relative_to(directory)
        except (ValueError, OSError):
            return False

    @staticmethod
    def _has_symlink_in_path(path: str, directory: str) -> bool:
        """Detect symlinks in the portion of *path* below *directory*.

        Only segments below *directory* are inspected; the directory itself
        and anything above it are not checked.

        **Precondition:** *path* must be a descendant of *directory*.
        Call :meth:`_is_path_within_directory` first to verify containment.

        Args:
            path: Absolute path to inspect.
            directory: Root directory; segments above it are not checked.

        Returns:
            ``True`` if any intermediate segment below *directory* is a symlink.

        Raises:
            ValueError: If *path* is not relative to *directory*.
        """
        dir_path = Path(directory)
        try:
            relative = Path(path).relative_to(dir_path)
        except ValueError as exc:
            raise ValueError(f"path {path!r} does not start with directory {directory!r}") from exc

        current = dir_path
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                return True
        return False

    def _discover_resource_files(
        self,
        skill_dir_path: str,
        skill_name: str,
    ) -> list[str]:
        """Recursively scan a skill directory for resource files matching configured extensions.

        Scans the skill directory up to the configured search depth for files
        whose extension matches the allowed resource extensions, excluding
        ``SKILL.md`` itself.  Each candidate is validated against path-traversal
        and symlink-escape checks; unsafe files are skipped with a warning.
        If a ``resource_filter`` predicate is configured, files that do not
        satisfy it are excluded.

        Args:
            skill_dir_path: Absolute path to the skill directory to scan.
            skill_name: The skill name (from frontmatter) for filter context.

        Returns:
            Sorted relative resource paths (forward-slash-separated) for every
            discovered file that passes security and filter checks.
        """
        skill_dir = Path(skill_dir_path).absolute()
        root_directory_path = str(skill_dir)
        resources: list[str] = []
        normalized_extensions = {e.lower() for e in self._resource_extensions}

        self._scan_directory_for_resources(
            target_dir=skill_dir,
            skill_dir=skill_dir,
            root_directory_path=root_directory_path,
            skill_name=skill_name,
            normalized_extensions=normalized_extensions,
            resources=resources,
            current_depth=1,
        )

        resources.sort()
        return resources

    def _scan_directory_for_resources(
        self,
        target_dir: Path,
        skill_dir: Path,
        root_directory_path: str,
        skill_name: str,
        normalized_extensions: set[str],
        resources: list[str],
        current_depth: int,
    ) -> None:
        """Recursively scan a directory for resource files.

        Args:
            target_dir: The directory to scan at this level.
            skill_dir: The skill root directory (for relative path computation).
            root_directory_path: String form of the skill root (for security checks).
            skill_name: Skill name for filter predicate context.
            normalized_extensions: Lowercased allowed extensions.
            resources: Accumulator list for discovered relative paths.
            current_depth: Current recursion depth (starts at 1).
        """
        if current_depth > self._search_depth:
            return

        is_root = target_dir == skill_dir

        # Directory-level symlink check for non-root directories
        if not is_root:
            resolved_target = str(Path(os.path.normpath(target_dir)).absolute())
            if not FileSkillsSource._is_path_within_directory(resolved_target, root_directory_path):
                logger.warning(
                    "Skipping resource directory '%s': resolves outside skill directory '%s'",
                    target_dir,
                    root_directory_path,
                )
                return

            if FileSkillsSource._has_symlink_in_path(resolved_target, root_directory_path):
                logger.warning(
                    "Skipping resource directory '%s': symlink detected in path under skill directory '%s'",
                    target_dir,
                    root_directory_path,
                )
                return

        try:
            entries = list(target_dir.iterdir())
        except OSError:
            logger.warning(
                "Failed to list resource directory '%s' in skill directory '%s'; skipping.",
                target_dir,
                root_directory_path,
            )
            return

        subdirectories: list[Path] = []

        for entry in entries:
            if entry.is_dir():
                subdirectories.append(entry)
                continue

            if not entry.is_file():
                continue

            if entry.name.upper() == SKILL_FILE_NAME.upper():
                continue

            if entry.suffix.lower() not in normalized_extensions:
                continue

            resource_full_path = str(Path(os.path.normpath(entry)).absolute())

            # Containment check: file must resolve within the skill directory
            if not FileSkillsSource._is_path_within_directory(resource_full_path, root_directory_path):
                logger.warning(
                    "Skipping resource '%s': resolves outside skill directory '%s'",
                    entry,
                    root_directory_path,
                )
                continue

            if FileSkillsSource._has_symlink_in_path(resource_full_path, root_directory_path):
                logger.warning(
                    "Skipping resource '%s': symlink detected in path under skill directory '%s'",
                    entry,
                    root_directory_path,
                )
                continue

            rel_path = FileSkillsSource._normalize_resource_path(str(entry.relative_to(skill_dir)))

            # Apply user-provided filter predicate
            if self._resource_filter is not None and not self._resource_filter(skill_name, rel_path):
                continue

            resources.append(rel_path)

        # Recurse into subdirectories if within depth limit.
        # Subdirectories that contain their own SKILL.md are NOT skipped: a nested
        # SKILL.md is not an independent skill (see _discover_skill_directories), so
        # its contents belong to this skill.
        if current_depth < self._search_depth:
            for subdir in subdirectories:
                self._scan_directory_for_resources(
                    target_dir=subdir,
                    skill_dir=skill_dir,
                    root_directory_path=root_directory_path,
                    skill_name=skill_name,
                    normalized_extensions=normalized_extensions,
                    resources=resources,
                    current_depth=current_depth + 1,
                )

    def _discover_script_files(
        self,
        skill_dir_path: str,
        skill_name: str,
    ) -> list[str]:
        """Recursively scan a skill directory for script files matching configured extensions.

        Scans the skill directory up to the configured search depth for files
        whose extension matches the allowed script extensions.  Each candidate
        is validated against path-traversal and symlink-escape checks; unsafe
        files are skipped with a warning.  If a ``script_filter`` predicate
        is configured, files that do not satisfy it are excluded.

        Args:
            skill_dir_path: Absolute path to the skill directory to scan.
            skill_name: The skill name (from frontmatter) for filter context.

        Returns:
            Sorted relative script paths (forward-slash-separated) for every
            discovered file that passes security and filter checks.
        """
        skill_dir = Path(skill_dir_path).absolute()
        root_directory_path = str(skill_dir)
        scripts: list[str] = []
        normalized_extensions = {e.lower() for e in self._script_extensions}

        self._scan_directory_for_scripts(
            target_dir=skill_dir,
            skill_dir=skill_dir,
            root_directory_path=root_directory_path,
            skill_name=skill_name,
            normalized_extensions=normalized_extensions,
            scripts=scripts,
            current_depth=1,
        )

        scripts.sort()
        return scripts

    def _scan_directory_for_scripts(
        self,
        target_dir: Path,
        skill_dir: Path,
        root_directory_path: str,
        skill_name: str,
        normalized_extensions: set[str],
        scripts: list[str],
        current_depth: int,
    ) -> None:
        """Recursively scan a directory for script files.

        Args:
            target_dir: The directory to scan at this level.
            skill_dir: The skill root directory (for relative path computation).
            root_directory_path: String form of the skill root (for security checks).
            skill_name: Skill name for filter predicate context.
            normalized_extensions: Lowercased allowed extensions.
            scripts: Accumulator list for discovered relative paths.
            current_depth: Current recursion depth (starts at 1).
        """
        if current_depth > self._search_depth:
            return

        is_root = target_dir == skill_dir

        # Directory-level symlink check for non-root directories
        if not is_root:
            resolved_target = str(Path(os.path.normpath(target_dir)).absolute())
            if not FileSkillsSource._is_path_within_directory(resolved_target, root_directory_path):
                logger.warning(
                    "Skipping script directory '%s': resolves outside skill directory '%s'",
                    target_dir,
                    root_directory_path,
                )
                return

            if FileSkillsSource._has_symlink_in_path(resolved_target, root_directory_path):
                logger.warning(
                    "Skipping script directory '%s': symlink detected in path under skill directory '%s'",
                    target_dir,
                    root_directory_path,
                )
                return

        try:
            entries = list(target_dir.iterdir())
        except OSError:
            logger.warning(
                "Failed to list script directory '%s' in skill directory '%s'; skipping.",
                target_dir,
                root_directory_path,
            )
            return

        subdirectories: list[Path] = []

        for entry in entries:
            if entry.is_dir():
                subdirectories.append(entry)
                continue

            if not entry.is_file():
                continue

            if entry.suffix.lower() not in normalized_extensions:
                continue

            script_full_path = str(Path(os.path.normpath(entry)).absolute())

            # Containment check: file must resolve within the skill directory
            if not FileSkillsSource._is_path_within_directory(script_full_path, root_directory_path):
                logger.warning(
                    "Skipping script '%s': resolves outside skill directory '%s'",
                    entry,
                    root_directory_path,
                )
                continue

            if FileSkillsSource._has_symlink_in_path(script_full_path, root_directory_path):
                logger.warning(
                    "Skipping script '%s': symlink detected in path under skill directory '%s'",
                    entry,
                    root_directory_path,
                )
                continue

            rel_path = FileSkillsSource._normalize_resource_path(str(entry.relative_to(skill_dir)))

            # Apply user-provided filter predicate
            if self._script_filter is not None and not self._script_filter(skill_name, rel_path):
                continue

            scripts.append(rel_path)

        # Recurse into subdirectories if within depth limit.
        # Subdirectories that contain their own SKILL.md are NOT skipped: a nested
        # SKILL.md is not an independent skill (see _discover_skill_directories), so
        # its contents belong to this skill.
        if current_depth < self._search_depth:
            for subdir in subdirectories:
                self._scan_directory_for_scripts(
                    target_dir=subdir,
                    skill_dir=skill_dir,
                    root_directory_path=root_directory_path,
                    skill_name=skill_name,
                    normalized_extensions=normalized_extensions,
                    scripts=scripts,
                    current_depth=current_depth + 1,
                )

    @staticmethod
    def _get_validated_resource_path(skill_dir: str, resource_name: str) -> str:
        """Resolve and validate a resource file path within a skill directory.

        Normalizes *resource_name*, resolves it against *skill_dir*, and
        validates that the result stays within the skill directory and does
        not traverse any symlinks.

        Args:
            skill_dir: Absolute path to the owning skill directory.
            resource_name: Relative path of the resource within the skill directory.

        Returns:
            The validated absolute path to the resource file.

        Raises:
            ValueError: If *skill_dir* is not an absolute path, the resolved path
                escapes the skill directory, the file does not exist, or a symlink
                is detected in the path.
        """
        if not os.path.isabs(skill_dir):
            raise ValueError(f"skill_dir must be an absolute path, got: '{skill_dir}'")

        resource_name = FileSkillsSource._normalize_resource_path(resource_name)

        resource_full_path = os.path.normpath(Path(skill_dir) / resource_name)
        root_directory_path = os.path.normpath(skill_dir)

        if not FileSkillsSource._is_path_within_directory(resource_full_path, root_directory_path):
            raise ValueError(f"Resource file '{resource_name}' references a path outside the skill directory.")

        if not Path(resource_full_path).is_file():
            raise ValueError(f"Resource file '{resource_name}' not found in skill directory '{skill_dir}'.")

        if FileSkillsSource._has_symlink_in_path(resource_full_path, root_directory_path):
            raise ValueError(f"Resource file '{resource_name}' has a symlink in its path; symlinks are not allowed.")

        return resource_full_path

    @staticmethod
    def _validate_skill_metadata(
        name: str | None,
        description: str | None,
        source: str,
        compatibility: str | None = None,
    ) -> str | None:
        """Validate a skill's name, description, and compatibility against naming rules.

        Enforces length limits, character-set restrictions, and non-emptiness
        for both file-based and code-defined skills.

        Args:
            name: Skill name to validate.
            description: Skill description to validate.
            source: Human-readable label for diagnostics (e.g. a file path
                or ``"code skill"``).
            compatibility: Optional compatibility value to validate.

        Returns:
            A diagnostic error string if validation fails, or ``None`` if valid.
        """
        if not name or not name.strip():
            return f"Skill from '{source}' is missing a name."

        if len(name) > MAX_NAME_LENGTH or not VALID_NAME_RE.match(name):
            return (
                f"Skill from '{source}' has an invalid name '{name}': Must be {MAX_NAME_LENGTH} characters or fewer, "
                "using only lowercase letters, numbers, and hyphens, and must not start or end with a hyphen "
                "or contain consecutive hyphens."
            )

        if not description or not description.strip():
            return f"Skill '{name}' from '{source}' is missing a description."

        if len(description) > MAX_DESCRIPTION_LENGTH:
            return (
                f"Skill '{name}' from '{source}' has an invalid description: "
                f"Must be {MAX_DESCRIPTION_LENGTH} characters or fewer."
            )

        if compatibility is not None and len(compatibility) > MAX_COMPATIBILITY_LENGTH:
            return (
                f"Skill '{name}' from '{source}' has an invalid compatibility: "
                f"Must be {MAX_COMPATIBILITY_LENGTH} characters or fewer."
            )

        return None

    @staticmethod
    def _extract_frontmatter(
        content: str,
        skill_file_path: str,
    ) -> SkillFrontmatter | None:
        """Extract and validate YAML frontmatter from a SKILL.md file.

        Parses the ``---``-delimited frontmatter block for all
        `agentskills.io specification <https://agentskills.io/specification>`_
        fields: ``name``, ``description``, ``license``, ``compatibility``,
        ``allowed-tools``, and ``metadata``.

        Args:
            content: Raw text content of the SKILL.md file.
            skill_file_path: Path to the file (used in diagnostic messages only).

        Returns:
            A :class:`SkillFrontmatter` on success, or ``None`` if the
            frontmatter is missing, malformed, or fails validation.
        """
        match = FRONTMATTER_RE.search(content)
        if not match:
            logger.error("SKILL.md at '%s' does not contain valid YAML frontmatter delimited by '---'", skill_file_path)
            return None

        yaml_content = match.group(1).strip()
        name: str | None = None
        description: str | None = None
        license_value: str | None = None
        compatibility: str | None = None
        allowed_tools: str | None = None

        for kv_match in YAML_KV_RE.finditer(yaml_content):
            key = kv_match.group(1)
            value = (
                kv_match.group(2) if kv_match.group(2) is not None else _parse_yaml_scalar_value(yaml_content, kv_match)
            )

            key_lower = key.lower()
            if key_lower == "name":
                name = value
            elif key_lower == "description":
                description = value
            elif key_lower == "license":
                license_value = value
            elif key_lower == "compatibility":
                compatibility = value
            elif key_lower == "allowed-tools":
                allowed_tools = value

        # Parse metadata block (indented key-value pairs under "metadata:").
        metadata: dict[str, str] | None = None
        metadata_match = YAML_METADATA_BLOCK_RE.search(yaml_content)
        if metadata_match:
            metadata = {}
            for kv_match in YAML_INDENTED_KV_RE.finditer(metadata_match.group(1)):
                mk = kv_match.group(1)
                mv = kv_match.group(2) if kv_match.group(2) is not None else kv_match.group(3)
                metadata[mk] = mv

        error = FileSkillsSource._validate_skill_metadata(name, description, skill_file_path, compatibility)
        if error:
            logger.error(error)
            return None

        # name and description are guaranteed non-None after validation;
        # SkillFrontmatter re-validates as a defense-in-depth invariant.
        return SkillFrontmatter(
            name=cast(str, name),
            description=cast(str, description),
            license=license_value,
            compatibility=compatibility,
            allowed_tools=allowed_tools,
            metadata=metadata,
        )

    @staticmethod
    def _read_and_parse_skill_file(
        skill_dir_path: str,
    ) -> tuple[SkillFrontmatter, str] | None:
        """Read and parse the SKILL.md file in *skill_dir_path*.

        Args:
            skill_dir_path: Absolute path to the directory containing ``SKILL.md``.

        Returns:
            A ``(frontmatter, content)`` tuple where *content* is the
            full raw file text, or ``None`` if the file cannot be read or
            its frontmatter is invalid.
        """
        skill_file = Path(skill_dir_path) / SKILL_FILE_NAME

        try:
            content = skill_file.read_text(encoding="utf-8")
        except OSError:
            logger.error("Failed to read SKILL.md at '%s'", skill_file)
            return None

        frontmatter = FileSkillsSource._extract_frontmatter(content, str(skill_file))
        if frontmatter is None:
            return None

        dir_name = Path(skill_dir_path).name
        if frontmatter.name != dir_name:
            logger.error(
                "SKILL.md at '%s' has frontmatter name '%s' that does not match the directory name '%s'; skipping.",
                skill_file,
                frontmatter.name,
                dir_name,
            )
            return None

        return frontmatter, content

    @staticmethod
    def _discover_skill_directories(skill_paths: Sequence[str]) -> list[str]:
        """Return absolute paths of all directories that contain a ``SKILL.md`` file.

        Recursively searches each root path up to :data:`MAX_SEARCH_DEPTH`. Once a
        ``SKILL.md`` is found in a directory, that directory is the skill root and the
        search does not descend into its subdirectories: everything beneath a skill
        boundary is part of that skill, not an independent skill root.

        Args:
            skill_paths: Root directory paths to search.

        Returns:
            Absolute paths to directories containing ``SKILL.md``.
        """
        discovered: list[str] = []

        def _search(directory: str, current_depth: int) -> None:
            dir_path = Path(directory)
            if (dir_path / SKILL_FILE_NAME).is_file():
                # This directory is a skill root. Subdirectories are part of this
                # skill and must not be treated as independent skill roots.
                discovered.append(str(dir_path.absolute()))
                return

            if current_depth >= MAX_SEARCH_DEPTH:
                return

            try:
                entries = list(dir_path.iterdir())
            except OSError:
                return

            for entry in entries:
                if entry.is_dir():
                    _search(str(entry), current_depth + 1)

        for root_dir in skill_paths:
            if not root_dir or not root_dir.strip() or not Path(root_dir).is_dir():
                continue
            _search(root_dir, current_depth=0)

        return discovered


class InMemorySkillsSource(SkillsSource):
    """Skill source that holds pre-built :class:`Skill` instances in memory.

    Accepts any :class:`Skill` instances (e.g. :class:`InlineSkill`,
    :class:`FileSkill`).  Skills are assumed to be valid (validated at
    construction time by the concrete class).

    Examples:
        .. code-block:: python

            skill = InlineSkill(
                name="my-skill",
                description="Example skill",
                instructions="Instructions here...",
            )
            source = InMemorySkillsSource([skill])
            # `context` is normally supplied by SkillsProvider at runtime.
            context = SkillsSourceContext(agent=agent)
            skills = await source.get_skills(context)
    """

    def __init__(self, skills: Sequence[Skill]) -> None:
        """Initialize an InMemorySkillsSource.

        Args:
            skills: :class:`Skill` instances to serve from this source.
        """
        self._skills = list(skills)

    async def get_skills(self, context: SkillsSourceContext) -> list[Skill]:
        """Return the stored skills.

        Args:
            context: Contextual information about the agent and session
                requesting skills. Accepted for the source contract; this
                source returns the same stored skills regardless of context.

        Returns:
            A list of :class:`Skill` instances.
        """
        mark_feature_used(FeatureIndex.CORE_IN_MEMORY_SKILLS_SOURCE)
        return self._skills


class DelegatingSkillsSource(SkillsSource, ABC):
    """Abstract decorator base that wraps an inner skill source.

    Subclass this to implement cross-cutting concerns (filtering, caching,
    deduplication, etc.) as composable decorators over any
    :class:`SkillsSource`.

    Attributes:
        inner_source: The wrapped source that this decorator delegates to.
    """

    def __init__(self, inner_source: SkillsSource) -> None:
        """Initialize a DelegatingSkillsSource.

        Args:
            inner_source: The source to wrap and delegate to.
        """
        self._inner_source = inner_source

    @property
    def inner_source(self) -> SkillsSource:
        """The wrapped inner skill source."""
        return self._inner_source

    async def get_skills(self, context: SkillsSourceContext) -> list[Skill]:
        """Delegate to the inner source.

        Subclasses should override this to intercept the results.

        Args:
            context: Contextual information about the agent and session
                requesting skills, forwarded to the inner source.

        Returns:
            Skills from the inner source.
        """
        return await self._inner_source.get_skills(context)


class DeduplicatingSkillsSource(DelegatingSkillsSource):
    """Decorator that deduplicates skills by name (case-insensitive).

    When multiple skills share the same name (ignoring case), only the
    first occurrence is kept and later duplicates are skipped with a
    warning log.

    This is useful when composing multiple sources, where the same skill
    name might appear in more than one source.

    Examples:
        .. code-block:: python

            deduped = DeduplicatingSkillsSource(inner_source)
            # `context` is normally supplied by SkillsProvider at runtime.
            context = SkillsSourceContext(agent=agent)
            skills = await deduped.get_skills(context)
    """

    def __init__(self, inner_source: SkillsSource) -> None:
        """Initialize a DeduplicatingSkillsSource.

        Args:
            inner_source: The source whose results will be deduplicated.
        """
        super().__init__(inner_source)

    async def get_skills(self, context: SkillsSourceContext) -> list[Skill]:
        """Return deduplicated skills (first-one-wins by name).

        Args:
            context: Contextual information about the agent and session
                requesting skills, forwarded to the inner source.

        Returns:
            A list of :class:`Skill` instances with duplicate names removed.
        """
        skills = await self._inner_source.get_skills(context)
        seen: dict[str, Skill] = {}
        result: list[Skill] = []

        for skill in skills:
            key = skill.frontmatter.name.lower()
            if key in seen:
                logger.warning(
                    "Duplicate skill name '%s': skill skipped in favor of existing skill '%s'",
                    skill.frontmatter.name,
                    seen[key].frontmatter.name,
                )
                continue
            seen[key] = skill
            result.append(skill)

        return result


class FilteringSkillsSource(DelegatingSkillsSource):
    """Decorator that filters skills from an inner source by predicate.

    Only skills for which *predicate* returns ``True`` are included in the
    result.  The predicate receives each :class:`Skill` together with the
    :class:`SkillsSourceContext` for the current invocation, enabling
    context-aware filtering (for example, per-agent skill selection).

    Examples:
        .. code-block:: python

            filtered = FilteringSkillsSource(
                inner_source=my_source,
                predicate=lambda skill, context: skill.frontmatter.name != "internal",
            )
            # `source_context` is normally supplied by SkillsProvider at runtime.
            source_context = SkillsSourceContext(agent=agent)
            skills = await filtered.get_skills(source_context)
    """

    def __init__(
        self,
        inner_source: SkillsSource,
        predicate: Callable[[Skill, SkillsSourceContext], bool],
    ) -> None:
        """Initialize a FilteringSkillsSource.

        Args:
            inner_source: The source to filter.
            predicate: A callable that receives a :class:`Skill` and the
                :class:`SkillsSourceContext` and returns ``True`` to keep the
                skill or ``False`` to exclude it.
        """
        super().__init__(inner_source)
        self._predicate = predicate

    async def get_skills(self, context: SkillsSourceContext) -> list[Skill]:
        """Return only skills that match the predicate.

        Args:
            context: Contextual information about the agent and session
                requesting skills, forwarded to the inner source and passed to
                the predicate.

        Returns:
            A filtered list of :class:`Skill` instances.
        """
        skills = await self._inner_source.get_skills(context)
        return [s for s in skills if self._predicate(s, context)]


class CachingSkillsSource(DelegatingSkillsSource):
    """Decorator that caches the skills list returned by an inner source.

    The first call to :meth:`get_skills` queries the inner source and caches
    the resulting list; subsequent calls return the cached list without
    re-querying the inner source.  This makes caching a composable layer in
    the skills-source pipeline rather than logic baked into a provider.

    Caching is useful when the inner source is expensive to query — for
    example, a :class:`FileSkillsSource` that walks the filesystem on every
    call, or an :class:`MCPSkillsSource` that makes network requests.  Skills
    are typically static discovery metadata, so querying once and reusing the
    result is a pure performance win.

    Concurrency: concurrent callers for the same cache key share a single
    in-flight fetch, so the inner source is queried at most once per key even
    under concurrent access.  If a fetch fails (or is cancelled), the cache is
    not updated, so the next call retries: an initial failure leaves the cache
    empty, and a refresh failure (see below) keeps the previously cached list.

    Refresh interval: by default a cached list never expires and the inner
    source is queried only once per key. Pass a *refresh_interval* to treat a
    cached list as stale once it is older than the interval; the next call for
    that key then re-queries the inner source and replaces the cached list.
    This is useful for inner sources whose skills can change over the process
    lifetime — for example an :class:`MCPSkillsSource` whose remote server
    updates its advertised skills. A ``timedelta`` of zero or a negative
    duration makes every cached list immediately stale, effectively disabling
    caching (the inner source is queried on every call). A failed refresh
    leaves the previous cached list in place and keeps retrying on subsequent
    calls until one succeeds.

    Cache isolation: by default all callers share a single cache bucket. Pass
    a *cache_isolation_key_selector* to derive a cache key from the
    :class:`SkillsSourceContext`, so context-aware inner sources (which may
    return different skills per agent) are cached separately per key. The key
    should be low-cardinality and stable (for example, an agent name or tenant
    id); high-cardinality keys such as per-session ids can cause the cache to
    grow without bound. Returning ``None`` from the selector (or leaving it
    ``None``) uses the shared bucket.

    Examples:
        .. code-block:: python

            cached = CachingSkillsSource(expensive_source)
            # `context` is normally supplied by SkillsProvider at runtime.
            context = SkillsSourceContext(agent=agent)
            skills = await cached.get_skills(context)  # queries the inner source
            skills = await cached.get_skills(context)  # returns the cached list

        Isolating the cache per agent:

        .. code-block:: python

            cached = CachingSkillsSource(
                expensive_source,
                cache_isolation_key_selector=lambda context: context.agent.name,
            )

        Refreshing the cache periodically:

        .. code-block:: python

            from datetime import timedelta

            cached = CachingSkillsSource(
                expensive_source,
                refresh_interval=timedelta(minutes=5),
            )
    """

    _SHARED_CACHE_KEY: Final[str] = "__caching_skills_source_shared__"

    def __init__(
        self,
        inner_source: SkillsSource,
        *,
        cache_isolation_key_selector: Callable[[SkillsSourceContext], str | None] | None = None,
        refresh_interval: timedelta | None = None,
    ) -> None:
        """Initialize a CachingSkillsSource.

        Args:
            inner_source: The source whose results will be cached.

        Keyword Args:
            cache_isolation_key_selector: Optional callable that derives a cache
                key from the :class:`SkillsSourceContext`. When ``None`` (the
                default), or when the callable returns ``None``, skills are
                stored in a single shared bucket. Otherwise skills are cached
                under the returned key. Keys should be low-cardinality and
                stable to keep the cache bounded.
            refresh_interval: Optional duration after which a cached skills list
                is considered stale and re-fetched from the inner source on the
                next request. When ``None`` (the default), cached results never
                expire and the inner source is queried only once per cache key.
                A zero or negative ``timedelta`` makes every cached result
                immediately stale, effectively disabling caching.
        """
        super().__init__(inner_source)
        self._cache_isolation_key_selector = cache_isolation_key_selector
        self._refresh_interval = refresh_interval
        self._locks_guard = asyncio.Lock()
        self._locks: dict[str, asyncio.Lock] = {}
        self._cached_skills: dict[str, list[Skill]] = {}
        self._cache_timestamps: dict[str, float] = {}

    def _resolve_cache_key(self, context: SkillsSourceContext) -> str:
        """Resolve the cache bucket key for *context*."""
        if self._cache_isolation_key_selector is not None:
            selected = self._cache_isolation_key_selector(context)
            if selected is not None:
                return selected
        return self._SHARED_CACHE_KEY

    def _get_fresh_cached(self, key: str) -> list[Skill] | None:
        """Return the cached skills for *key* when present and still fresh.

        Returns ``None`` when nothing is cached for *key*, or when a
        *refresh_interval* is configured and the cached list is older than the
        interval (so the caller re-queries the inner source).
        """
        cached = self._cached_skills.get(key)
        if cached is None:
            return None
        if self._refresh_interval is not None:
            age = time.monotonic() - self._cache_timestamps.get(key, 0.0)
            if age >= self._refresh_interval.total_seconds():
                return None
        return cached

    async def _get_lock(self, key: str) -> asyncio.Lock:
        """Return the per-key lock, creating it under a guard if needed."""
        async with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    async def get_skills(self, context: SkillsSourceContext) -> list[Skill]:
        """Return the inner source's skills, caching them per key on first call.

        Args:
            context: Contextual information about the agent and session
                requesting skills. Used to resolve the cache key (via
                *cache_isolation_key_selector*) and forwarded to the inner
                source.

        Returns:
            The cached list of :class:`Skill` instances for the resolved cache
            key.  On the first call for a key (or the first call after the
            configured *refresh_interval* has elapsed) the inner source is
            queried; otherwise the cached list is returned.  If the query
            fails, the cache is not updated and the next call retries.
        """
        key = self._resolve_cache_key(context)

        cached = self._get_fresh_cached(key)
        if cached is not None:
            return cached

        lock = await self._get_lock(key)
        async with lock:
            # Another coroutine may have populated (or refreshed) the cache
            # while we awaited the lock; re-check before querying the inner
            # source.
            cached = self._get_fresh_cached(key)
            if cached is not None:
                return cached

            skills = await self._inner_source.get_skills(context)
            self._cached_skills[key] = skills
            self._cache_timestamps[key] = time.monotonic()
            return skills


class AggregatingSkillsSource(SkillsSource):
    """Skill source that composes multiple sources into one."""

    def __init__(self, sources: Sequence[SkillsSource]) -> None:
        self._sources = list(sources)

    async def get_skills(self, context: SkillsSourceContext) -> list[Skill]:
        result: list[Skill] = []
        for source in self._sources:
            skills = await source.get_skills(context)
            result.extend(skills)
        return result


# region MCP Skills


def _mcp_any_url(uri: str) -> AnyUrl:
    """Convert a string URI to a :class:`pydantic.AnyUrl` for MCP client calls."""
    from pydantic import AnyUrl as _AnyUrl

    return _AnyUrl(uri)


def _is_mcp_resource_not_found(ex: Exception) -> bool:
    """Return ``True`` when *ex* is an :class:`McpError` indicating a missing resource.

    Two codes are treated as "not found":

    * ``-32002`` — the MCP-spec "Resource not found" code returned by a
      compliant server when the URI does not exist. Not exported as a
      constant from ``mcp.types`` but defined by the resources subprotocol.
    * ``METHOD_NOT_FOUND`` (``-32601``) — the server does not implement
      ``resources/read`` at all, which for the skills source is functionally
      equivalent to "no skills available."

    All other codes — ``INVALID_PARAMS``, ``INTERNAL_ERROR``, ``PARSE_ERROR``,
    ``CONNECTION_CLOSED``, auth rejections, and generic handler errors
    (code ``0``) — are treated as real failures so that a misconfigured
    token or crashing server is not silently mistaken for "the server has no
    skills."
    """
    from mcp.shared.exceptions import McpError as _McpError

    if not isinstance(ex, _McpError):
        return False
    from mcp.types import METHOD_NOT_FOUND as _METHOD_NOT_FOUND

    return ex.error.code in {-32002, _METHOD_NOT_FOUND}


def _mcp_join_text(result: ReadResourceResult) -> str:
    """Join all :class:`TextResourceContents` items in a result into a single string."""
    from mcp.types import TextResourceContents as _TextResourceContents

    return "\n".join(c.text for c in result.contents if isinstance(c, _TextResourceContents))


class _McpSkillIndexEntry:  # ruff:ignore[class-as-data-structure]
    """A single entry in the ``skill://index.json`` discovery document.

    All fields are optional to support lenient deserialization; callers
    validate required fields before use.
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        type: str | None = None,
        description: str | None = None,
        url: str | None = None,
        digest: str | None = None,
    ) -> None:
        self.name = name
        self.type = type
        self.description = description
        self.url = url
        self.digest = digest


class _McpSkillIndex:
    """DTO for the ``skill://index.json`` discovery document.

    Represents the Agent Skills Discovery v0.2.0 schema as bound to MCP
    by SEP-2640.
    """

    def __init__(
        self,
        *,
        schema: str | None = None,
        skills: list[_McpSkillIndexEntry] | None = None,
    ) -> None:
        self.schema = schema
        self.skills: list[_McpSkillIndexEntry] = skills if skills is not None else []


def _parse_mcp_skill_index(text: str) -> _McpSkillIndex:
    """Parse a JSON string into a :class:`_McpSkillIndex`.

    Args:
        text: Raw JSON text from ``skill://index.json``.

    Returns:
        A populated :class:`_McpSkillIndex` instance.

    Raises:
        json.JSONDecodeError: If the text is not valid JSON.
        ValueError: If the top-level value is not a JSON object.
    """
    raw: dict[str, Any] = json.loads(text)

    if not isinstance(raw, dict):
        raise ValueError("skill://index.json must be a JSON object")

    entries: list[_McpSkillIndexEntry] = []

    raw_skills: list[Any] = raw.get("skills") or []

    for item in raw_skills:
        if isinstance(item, dict):
            d = cast(dict[str, Any], item)

            entries.append(
                _McpSkillIndexEntry(
                    name=d.get("name"),
                    type=d.get("type"),
                    description=d.get("description"),
                    url=d.get("url"),
                    digest=d.get("digest"),
                )
            )

    return _McpSkillIndex(schema=raw.get("$schema"), skills=entries)


def _resolve_mcp_session_provider(
    client: ClientSession | None,
    session_provider: Callable[[], ClientSession] | None,
) -> Callable[[], ClientSession]:
    """Normalize the two MCP session inputs into a single session resolver.

    Callers supply **exactly one** of a fixed ``client`` or a
    ``session_provider`` callable. A fixed client is wrapped in a provider that
    always returns it; a provider is used as-is so the session is resolved on
    every call (reconnect-safe for sources whose underlying session is replaced
    over time, e.g. a reconnecting :class:`~agent_framework.MCPTool`).

    Args:
        client: A fixed MCP client session, or ``None``.
        session_provider: A callable returning the current MCP client session,
            or ``None``.

    Returns:
        A callable that returns the MCP client session to use.

    Raises:
        ValueError: If both or neither of *client* and *session_provider* are
            provided.
    """
    if client is not None and session_provider is not None:
        raise ValueError("Provide exactly one of 'client' or 'session_provider', not both.")
    if session_provider is not None:
        return session_provider
    if client is None:
        raise ValueError("Provide exactly one of 'client' or 'session_provider'.")
    fixed: ClientSession = client
    return lambda: fixed


@experimental(feature_id=ExperimentalFeature.MCP_SKILLS)
class MCPSkillResource(SkillResource):
    """A :class:`SkillResource` backed by content fetched from an MCP server.

    The :class:`~mcp.types.ReadResourceResult` is fetched eagerly by
    :meth:`MCPSkill.get_resource` at construction time; :meth:`read`
    extracts text or binary content from the result.
    """

    def __init__(self, *, name: str, result: ReadResourceResult) -> None:
        """Initialize an MCPSkillResource.

        Args:
            name: The resource name (e.g. a relative path or identifier).
            result: The result returned by the MCP server's ``resources/read`` request.
        """
        super().__init__(name=name)
        self._result = result

    async def read(self, **kwargs: Any) -> Any:
        """Read the resource content.

        Returns:
            A ``bytes`` object when the resource contains binary content,
            a ``str`` when it contains text, or ``None`` when the server
            returned no content blocks.
        """
        from mcp.types import BlobResourceContents, TextResourceContents

        for content in self._result.contents:
            if isinstance(content, BlobResourceContents):
                blob = content.blob
                # Strip data-URI prefix if present (some MCP servers send
                # full data URIs instead of raw base64).
                if blob.startswith("data:"):
                    blob = blob.split(",", 1)[-1]
                return base64.b64decode(blob)

        text = "\n".join(c.text for c in self._result.contents if isinstance(c, TextResourceContents))
        return text if text else None


@experimental(feature_id=ExperimentalFeature.MCP_SKILLS)
class MCPSkill(Skill):
    """A :class:`Skill` discovered from an MCP server exposing the Agent Skills convention.

    The skill is constructed from ``skill://index.json`` discovery metadata;
    :meth:`get_content` fetches the full ``SKILL.md`` content from the MCP
    server on demand via ``resources/read``.

    Per SEP-2640, resources referenced inside SKILL.md are fetched on demand
     via the originating MCP server: :meth:`get_resource` resolves a relative
    resource name against the skill's root URI, issues a ``resources/read``
     request, and returns an :class:`MCPSkillResource` with pre-fetched content.
    """

    _SKILL_MD_SUFFIX: Final[str] = "SKILL.md"

    def __init__(
        self,
        frontmatter: SkillFrontmatter,
        skill_md_uri: str,
        client: ClientSession | None = None,
        *,
        session_provider: Callable[[], ClientSession] | None = None,
    ) -> None:
        """Initialize an MCPSkill.

        Provide **exactly one** of *client* or *session_provider*.

        Args:
            frontmatter: The parsed frontmatter metadata for this skill.
            skill_md_uri: The full MCP resource URI of the ``SKILL.md`` resource
                (e.g. ``skill://unit-converter/SKILL.md``). The skill's root URI
                is derived by stripping the trailing ``SKILL.md`` segment.
            client: A fixed MCP client session used to fetch resources on demand.
                Use this when the session outlives the skill (e.g. a caller-owned
                long-lived session).

        Keyword Args:
            session_provider: A callable returning the current MCP client session,
                resolved on every fetch. Prefer this over *client* when the
                underlying session may be replaced over the skill's lifetime (for
                example, a reconnecting :class:`~agent_framework.MCPTool` whose
                ``session`` is swapped on reconnect), so a cached skill keeps
                using the live session instead of a closed one.

        Raises:
            ValueError: If both or neither of *client* and *session_provider* are
                provided.
        """
        self._frontmatter = frontmatter
        self._skill_md_uri = skill_md_uri
        self._skill_root_uri = self._compute_skill_root_uri(skill_md_uri)
        self._session_provider = _resolve_mcp_session_provider(client, session_provider)
        self._content: str | None = None

    @property
    def frontmatter(self) -> SkillFrontmatter:
        """The L1 discovery metadata for this skill."""
        return self._frontmatter

    async def get_content(self) -> str:
        """Get the full SKILL.md content from the MCP server.

        Fetches the content via ``resources/read`` on the first call and
        caches the result for subsequent calls.

        Returns:
            The SKILL.md content string.

        Raises:
            ValueError: If the MCP server returned no text content for the
                SKILL.md resource.
        """
        if self._content is not None:
            return self._content

        result = await self._session_provider().read_resource(_mcp_any_url(self._skill_md_uri))
        text = _mcp_join_text(result)
        if not text:
            raise ValueError(f"The MCP server returned no text content for SKILL.md resource '{self._skill_md_uri}'.")
        self._content = text
        return text

    async def get_resource(self, name: str) -> SkillResource | None:
        """Get a sibling resource by name from the MCP server.

        Resolves *name* as a relative path against the skill's root URI,
        issues a ``resources/read`` request to the MCP server, and returns
        an :class:`MCPSkillResource` with the pre-fetched content.

        Args:
            name: The resource name (e.g. ``references/checklist.md``).

        Returns:
            An :class:`MCPSkillResource`, or ``None`` when the name is empty
            or the resource does not exist on the server.
        """
        if not name or not name.strip():
            return None

        normalized = self._validate_resource_name(name)
        if normalized is None:
            return None

        uri = self._skill_root_uri + normalized
        try:
            result = await self._session_provider().read_resource(_mcp_any_url(uri))
        except Exception as ex:
            if _is_mcp_resource_not_found(ex):
                logger.debug("MCP resource '%s' not available: %s", uri, ex)
                return None
            raise

        return MCPSkillResource(name=name, result=result)

    @staticmethod
    def _validate_resource_name(name: str) -> str | None:
        """Validate a resource name and return the normalized form.

        Defense in depth: refuses names that could escape the skill root
        (absolute paths, embedded URI schemes, parent-traversal segments).
        The MCP server is the authority on URI resolution, but rejecting
        obviously unsafe shapes client-side avoids leaking escape attempts
        upstream.

        Args:
            name: The raw resource name to validate.

        Returns:
            The normalized name with backslashes replaced by forward slashes,
            or ``None`` if the name is unsafe.
        """
        normalized = name.replace("\\", "/")
        if normalized.startswith("/") or "://" in normalized or any(seg == ".." for seg in normalized.split("/")):
            logger.debug("Rejecting resource name with unsafe path components: %r", name)
            return None
        return normalized

    @staticmethod
    def _compute_skill_root_uri(skill_md_uri: str) -> str:
        """Strip the trailing ``SKILL.md`` from the URI to produce the skill root.

        If the URI doesn't end with ``SKILL.md``, ensures it ends with a
        trailing slash.
        """
        if skill_md_uri.endswith(MCPSkill._SKILL_MD_SUFFIX):
            return skill_md_uri[: -len(MCPSkill._SKILL_MD_SUFFIX)]
        if skill_md_uri.endswith("/"):
            return skill_md_uri
        return skill_md_uri + "/"


@experimental(feature_id=ExperimentalFeature.MCP_SKILLS)
class MCPSkillsSource(SkillsSource):
    """A :class:`SkillsSource` that discovers Agent Skills served over MCP.

    Discovery follows the SEP-2640 recommended approach: the source reads
    the well-known ``skill://index.json`` resource and constructs one
    :class:`MCPSkill` per ``skill-md`` entry directly from the entry's
    ``name``, ``description``, and ``url`` fields.

    The referenced ``SKILL.md`` resource is **not** read during discovery;
    the host fetches its body on demand via ``resources/read`` when the
    skill content is needed.

    Only index entries of type ``skill-md`` are supported; entries of any
    other type are silently skipped.

    If ``skill://index.json`` is absent, unreadable, empty, or fails to
    parse, this source returns an empty list.

    Security considerations:
        Discovering skills over MCP means an *external* MCP server controls
        what skill content (including instructions and, for script-capable
        skills, the scripts the agent may run) reaches the agent. This source
        is never enabled by default; it is only used when the caller connects
        it to a server explicitly. A compromised, malicious, or simply
        untrustworthy server can return adversarial skill content designed to
        manipulate the agent through indirect prompt injection, or
        instructions/scripts designed to exfiltrate data once loaded and, for
        script-capable skills, executed. Only connect this source to MCP
        servers you have vetted and trust, and treat their responses as
        untrusted input.

    Examples:
        .. code-block:: python

            from mcp.client.session import ClientSession

            source = MCPSkillsSource(client=session)
            # `context` is normally supplied by SkillsProvider at runtime.
            context = SkillsSourceContext(agent=agent)
            skills = await source.get_skills(context)
    """

    _INDEX_URI: Final[str] = "skill://index.json"
    _SKILL_MD_TYPE: Final[str] = "skill-md"

    def __init__(
        self,
        client: ClientSession | None = None,
        *,
        session_provider: Callable[[], ClientSession] | None = None,
    ) -> None:
        """Initialize an MCPSkillsSource.

        Provide **exactly one** of *client* or *session_provider*.

        Args:
            client: A fixed MCP client session connected to a server that exposes
                Agent Skills resources. Use this when the session outlives the
                source (e.g. a caller-owned long-lived session).

        Keyword Args:
            session_provider: A callable returning the current MCP client session,
                resolved on every discovery and on each skill's on-demand fetch.
                Prefer this over *client* when the underlying session may be
                replaced over time (for example, a reconnecting
                :class:`~agent_framework.MCPTool` whose ``session`` is swapped on
                reconnect), so cached skills keep using the live session. The
                provider is forwarded to every :class:`MCPSkill` this source
                creates.

        Raises:
            ValueError: If both or neither of *client* and *session_provider* are
                provided.
        """
        self._session_provider = _resolve_mcp_session_provider(client, session_provider)

    async def get_skills(self, context: SkillsSourceContext) -> list[Skill]:
        """Discover and return skills from the MCP server.

        Reads ``skill://index.json``, parses it, and creates an
        :class:`MCPSkill` for each valid ``skill-md`` entry.

        Args:
            context: Contextual information about the agent and session
                requesting skills. Accepted for the source contract; this
                source returns the same server-provided skills regardless of
                context.

        Returns:
            A list of discovered :class:`MCPSkill` instances.
        """
        mark_feature_used(FeatureIndex.CORE_MCP_SKILLS_SOURCE)
        index = await self._try_read_index()
        if index is None:
            return []

        skills: list[Skill] = []
        for entry in index.skills:
            result = self._try_create_skill(entry)
            if result is not None:
                skills.append(result)
                logger.info("Loaded MCP skill: %s", result.frontmatter.name)
            else:
                logger.debug(
                    "Skipping skill index entry '%s'",
                    entry.name or "(unnamed)",
                )

        logger.info("Successfully loaded %d skills from MCP server", len(skills))
        return skills

    async def _try_read_index(self) -> _McpSkillIndex | None:
        """Attempt to read and parse ``skill://index.json`` from the MCP server.

        Returns:
            A parsed :class:`_McpSkillIndex`, or ``None`` if the index is
            absent, empty, or malformed.
        """
        try:
            result = await self._session_provider().read_resource(_mcp_any_url(self._INDEX_URI))
        except Exception as ex:
            if _is_mcp_resource_not_found(ex):
                logger.debug("No skill://index.json resource available on MCP server: %s", ex)
                return None
            logger.warning("Failed to read skill://index.json from MCP server.", exc_info=True)
            raise

        index_text = _mcp_join_text(result)
        if not index_text:
            logger.debug("skill://index.json on MCP server returned empty/non-text contents")
            return None

        try:
            return _parse_mcp_skill_index(index_text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse skill://index.json JSON document.", exc_info=True)
            return None

    def _try_create_skill(self, entry: _McpSkillIndexEntry) -> MCPSkill | None:
        """Attempt to create an :class:`MCPSkill` from an index entry.

        Args:
            entry: A single entry from the skill index.

        Returns:
            An :class:`MCPSkill` if the entry is valid, or ``None`` if the
            entry should be skipped.
        """
        if entry.type != self._SKILL_MD_TYPE:
            logger.debug(
                "Skipping entry '%s': unsupported type '%s'",
                entry.name or "(unnamed)",
                entry.type or "(none)",
            )
            return None

        if not entry.name or not entry.name.strip():
            logger.debug("Skipping entry: missing required 'name' field")
            return None

        if not entry.description or not entry.description.strip():
            logger.debug("Skipping entry '%s': missing required 'description' field", entry.name)
            return None

        if not entry.url or not entry.url.strip():
            logger.debug("Skipping entry '%s': missing required 'url' field", entry.name)
            return None

        try:
            fm = SkillFrontmatter(name=entry.name, description=entry.description)
        except ValueError as ex:
            logger.debug("Skipping entry '%s': invalid metadata: %s", entry.name, ex)
            return None

        return MCPSkill(frontmatter=fm, skill_md_uri=entry.url, session_provider=self._session_provider)


# endregion
