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
:class:`FilteringSkillsSource`, and :class:`DeduplicatingSkillsSource`.

**Security:** file-based skill metadata is XML-escaped before prompt injection, and
file-based resource reads are guarded against path traversal and symlink escape.
Only use skills from trusted sources.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from html import escape as xml_escape
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, ClassVar, Final, Protocol, TypeVar, cast, runtime_checkable

from ._feature_stage import ExperimentalFeature, experimental
from ._sessions import ContextProvider
from ._tools import FunctionTool

if TYPE_CHECKING:
    from ._agents import SupportsAgentRun
    from ._sessions import AgentSession, SessionContext

logger = logging.getLogger(__name__)

# region Models


@experimental(feature_id=ExperimentalFeature.SKILLS)
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


@experimental(feature_id=ExperimentalFeature.SKILLS)
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


@experimental(feature_id=ExperimentalFeature.SKILLS)
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


@experimental(feature_id=ExperimentalFeature.SKILLS)
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
    ) -> None:
        """Initialize an InlineSkillScript.

        Args:
            name: Identifier for this script (e.g. ``"analyze"``).
            description: Optional human-readable summary.
            function: Callable (sync or async) that implements the script.
        """
        super().__init__(name=name, description=description)

        self.function = function
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

    async def run(self, skill: Skill, args: dict[str, Any] | list[str] | None = None, **kwargs: Any) -> Any:
        """Run the script by invoking the callable in-process.

        Args:
            skill: The skill that owns this script.
            args: Optional keyword arguments for the script, provided by the
                agent/LLM.  Must be a ``dict`` or ``None``; passing a
                ``list`` raises :class:`TypeError` because inline scripts
                bind arguments by keyword name.
            **kwargs: Runtime keyword arguments forwarded only to script
                functions that accept ``**kwargs``.

        Returns:
            The script execution result.

        Raises:
            TypeError: If ``args`` is a ``list`` (array-style arguments
                are only supported for file-based scripts).
        """
        if isinstance(args, list):
            raise TypeError(
                f"Inline script '{self.name}' requires keyword arguments (dict), "
                f"but received a list. Array-style arguments are only supported "
                f"for file-based scripts."
            )
        if self._accepts_kwargs:  # noqa: SIM108
            result = self.function(**(args or {}), **kwargs)
        else:
            result = self.function(**(args or {}))
        if inspect.isawaitable(result):
            return await result
        return result


@experimental(feature_id=ExperimentalFeature.SKILLS)
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


@experimental(feature_id=ExperimentalFeature.SKILLS)
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


@experimental(feature_id=ExperimentalFeature.SKILLS)
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

    Produces an XML document containing name, description, instructions,
    resources, and scripts elements.  Used by both :class:`InlineSkill`
    and :class:`ClassSkill` to generate their ``content`` property.

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

    if resources:
        resource_lines = "\n".join(_create_resource_element(r) for r in resources)
        result += f"\n\n<resources>\n{resource_lines}\n</resources>"

    if scripts:
        script_lines = "\n".join(_create_script_element(s) for s in scripts)
        result += f"\n\n<scripts>\n{script_lines}\n</scripts>"

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


@experimental(feature_id=ExperimentalFeature.SKILLS)
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
    ) -> None:
        """Initialize an InlineSkill.

        Args:
            frontmatter: Skill specification metadata (name, description,
                and optional spec fields). Construct a :class:`SkillFrontmatter`
                with the desired fields.
            instructions: The skill instructions text.
            resources: Pre-built resources to attach to this skill.
            scripts: Pre-built scripts to attach to this skill.
        """
        self._frontmatter = frontmatter

        self.instructions = instructions
        self._resources: list[SkillResource] = list(resources) if resources is not None else []
        self._scripts: list[SkillScript] = list(scripts) if scripts is not None else []
        self._cached_content: str | None = None

    @property
    def frontmatter(self) -> SkillFrontmatter:
        """The L1 discovery metadata for this skill."""
        return self._frontmatter

    async def get_content(self) -> str:
        """Synthesized XML content with name, description, instructions, resources, and scripts.

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


@experimental(feature_id=ExperimentalFeature.SKILLS)
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
    ) -> None:
        """Initialize a ClassSkill.

        Args:
            frontmatter: Skill specification metadata (name, description,
                and optional spec fields). Construct a :class:`SkillFrontmatter`
                with the desired fields.
        """
        self._frontmatter = frontmatter
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
                )
            )

        self._cached_scripts = scripts
        return list(self._cached_scripts)

    async def get_content(self) -> str:
        """Synthesized XML content containing name, description, instructions, resources, and scripts.

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


@experimental(feature_id=ExperimentalFeature.SKILLS)
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
        """The skill content with appended scripts block.

        When scripts are present, a ``<scripts>`` XML block is appended
        to the raw SKILL.md content so that the LLM can discover each
        script's ``<parameters_schema>``.

        The result is cached after the first access.  Adding scripts
        after the first access will not be reflected.

        Returns:
            The skill content string.
        """
        if self._cached_content is not None:
            return self._cached_content
        if not self._scripts:
            self._cached_content = self._content
        else:
            script_lines = "\n".join(_create_script_element(s) for s in self._scripts)
            self._cached_content = f"{self._content}\n\n<scripts>\n{script_lines}\n</scripts>"
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
@experimental(feature_id=ExperimentalFeature.SKILLS)
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

# "." means the skill directory root itself (files directly in the skill folder).
ROOT_DIRECTORY_INDICATOR: Final[str] = "."

# Standard subdirectory names per https://agentskills.io/specification#directory-structure
DEFAULT_RESOURCE_DIRECTORIES: Final[tuple[str, ...]] = ("references", "assets")
DEFAULT_SCRIPT_DIRECTORIES: Final[tuple[str, ...]] = ("scripts",)

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
    '   (e.g. `"style-guide"` not `"style-guide.md"`, `"references/FAQ"` not `"FAQ.md"`).\n'
)

SCRIPT_RUNNER_INSTRUCTIONS: Final[str] = (
    "- Use `run_skill_script` to run referenced scripts, using the name exactly as listed.\n"
    "- Pass script arguments inside `args` as a JSON object"
    ' (e.g. `args: {"length": 24}`), not as top-level tool parameters.\n'
)

# endregion

# region SkillsProvider

_TSkillsProvider = TypeVar("_TSkillsProvider", bound="SkillsProvider")


@experimental(feature_id=ExperimentalFeature.SKILLS)
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
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "agent_skills"

    def __init__(
        self,
        source: SkillsSource | Sequence[Skill] | Skill,
        *,
        instruction_template: str | None = None,
        require_script_approval: bool = False,
        disable_caching: bool = False,
        source_id: str | None = None,
    ) -> None:
        """Initialize a SkillsProvider.

        Accepts a :class:`SkillsSource`, a single :class:`Skill`, or a
        sequence of :class:`Skill` instances.  When skills are passed
        directly, they are automatically deduplicated.

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
            require_script_approval: When ``True``, skill script execution
                requires explicit user approval before running. Instead of
                executing immediately, the agent pauses and returns a
                ``function_approval_request`` via ``result.user_input_requests``.
                The application should present the request to the user, then
                call ``request.to_function_approval_response(approved=True)``
                (or ``False`` to reject) and pass the response back with
                ``agent.run(approval_response, session=session)``.
                Rejected scripts are not executed and the agent is informed
                the user declined. Defaults to ``False``.  See
                ``samples/02-agents/skills/script_approval/script_approval.py``
                for the full approval loop pattern.
            disable_caching: When ``True``, rebuilds tools and instructions
                from the source on every invocation instead of caching
                after the first build.  Defaults to ``False``.
            source_id: Unique identifier for this provider instance.
        """
        super().__init__(source_id or self.DEFAULT_SOURCE_ID)

        if isinstance(source, (str, Path)):
            raise TypeError(
                f"SkillsProvider does not accept path strings directly. "
                f"Use SkillsProvider.from_paths({source!r}) for file-based skills."
            )

        if isinstance(source, Skill):
            source = DeduplicatingSkillsSource(InMemorySkillsSource([source]))
        elif isinstance(source, SkillsSource):
            pass
        else:
            source = DeduplicatingSkillsSource(InMemorySkillsSource(list(source)))

        self._source = source
        self._instruction_template = instruction_template
        self._require_script_approval = require_script_approval
        self._disable_caching = disable_caching

        # Lazy-initialized via _get_or_create_context / _create_context
        self._cached_context: tuple[Sequence[Skill], str | None, list[FunctionTool]] | None = None

    @classmethod
    def from_paths(
        cls: type[_TSkillsProvider],
        skill_paths: str | Path | Sequence[str | Path],
        *,
        script_runner: SkillScriptRunner | None = None,
        resource_extensions: tuple[str, ...] | None = None,
        script_extensions: tuple[str, ...] | None = None,
        resource_directories: Sequence[str] | None = None,
        script_directories: Sequence[str] | None = None,
        instruction_template: str | None = None,
        require_script_approval: bool = False,
        disable_caching: bool = False,
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
            resource_directories: Relative directory paths to scan for
                resource files within each skill directory.  Use ``"."``
                to include files at the skill root level.  Defaults to
                ``("references", "assets")`` per the agentskills.io
                specification.
            script_directories: Relative directory paths to scan for
                script files within each skill directory.  Use ``"."``
                to include files at the skill root level.  Defaults to
                ``("scripts",)`` per the agentskills.io specification.
            instruction_template: Custom system-prompt template for
                advertising skills.  Must contain a ``{skills}`` placeholder.
                Uses a built-in template when ``None``.
            require_script_approval: When ``True``, skill script execution
                requires explicit user approval before running. Instead of
                executing immediately, the agent pauses and returns a
                ``function_approval_request`` via ``result.user_input_requests``.
                The application should present the request to the user, then
                call ``request.to_function_approval_response(approved=True)``
                (or ``False`` to reject) and pass the response back with
                ``agent.run(approval_response, session=session)``.
                Rejected scripts are not executed and the agent is informed
                the user declined. Defaults to ``False``.  See
                ``samples/02-agents/skills/script_approval/script_approval.py``
                for the full approval loop pattern.
            disable_caching: When ``True``, rebuilds tools and instructions
                from the source on every invocation instead of caching
                after the first build.
            source_id: Unique identifier for this provider instance.

        Returns:
            A configured :class:`SkillsProvider`.
        """
        source = DeduplicatingSkillsSource(
            FileSkillsSource(
                skill_paths,
                script_runner=script_runner,
                resource_extensions=resource_extensions,
                script_extensions=script_extensions,
                resource_directories=resource_directories,
                script_directories=script_directories,
            )
        )
        return cls(
            source,
            instruction_template=instruction_template,
            require_script_approval=require_script_approval,
            disable_caching=disable_caching,
            source_id=source_id,
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
                    "It must contain a '{skills}' placeholder and escape any literal"  # noqa: RUF027
                    " '{' or '}' "
                    "by doubling them ('{{' or '}}')."
                ) from exc
            if "__PROBE__" not in result:
                raise ValueError(
                    "The provided instruction_template must contain a '{skills}' placeholder."  # noqa: RUF027
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

    async def _create_context(self) -> tuple[Sequence[Skill], str | None, list[FunctionTool]]:
        """Build skills, instructions, and tools from the source.

        Always performs a fresh build by querying the source and
        constructing the instruction prompt and tool definitions.

        Returns:
            A tuple of ``(skills, instructions, tools)``.
        """
        skills = await self._source.get_skills()

        if not skills:
            return skills, None, []

        instructions = self._create_instructions(
            prompt_template=self._instruction_template,
            skills=skills,
        )

        tools = self._create_tools(
            skills=skills,
            require_script_approval=self._require_script_approval,
        )

        return skills, instructions, tools

    async def _get_or_create_context(self) -> tuple[Sequence[Skill], str | None, list[FunctionTool]]:
        """Return the cached context, building it on first call.

        On the first call, delegates to :meth:`_create_context` and caches
        the result.  Subsequent calls return the cached result immediately.
        If the first build fails, the cache is reset so the next call
        retries.

        Returns:
            A tuple of ``(skills, instructions, tools)``.
        """
        if self._cached_context is not None:
            return self._cached_context

        try:
            result = await self._create_context()
            self._cached_context = result
            return result
        except Exception:
            self._cached_context = None
            raise

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject skill instructions and tools into the session context.

        Called by the framework before the agent runs.  On the first call,
        loads skills from the configured source asynchronously and builds
        the instruction prompt and tool definitions.  When at least one
        skill is registered, appends the skill-list system prompt and the
        ``load_skill`` / ``read_skill_resource`` tools to *context*.

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
        if self._disable_caching:
            skills, instructions, tools = await self._create_context()
        else:
            skills, instructions, tools = await self._get_or_create_context()

        if not skills:
            return

        context.extend_instructions(self.source_id, instructions)  # type: ignore[arg-type]
        context.extend_tools(self.source_id, tools)

    def _create_tools(
        self,
        skills: Sequence[Skill],
        require_script_approval: bool = False,
    ) -> list[FunctionTool]:
        """Create the tool definitions for skill interaction.

        Always includes ``load_skill``, ``read_skill_resource``, and
        ``run_skill_script``.

        Args:
            skills: The skills to bind to tool handlers.
            require_script_approval: When ``True``, the
                ``run_skill_script`` tool pauses for user approval
                before each invocation.

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
                name="load_skill",
                description="Loads the full instructions for a specific skill.",
                func=_load,
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
                description=(
                    "Reads a resource associated with a skill, such as references, assets, or dynamic data."
                ),
                func=_read_resource,
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
                name="run_skill_script",
                description="Runs a script associated with a skill.",
                func=_run_script,
                approval_mode="always_require" if require_script_approval else "never_require",
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
                                        "Named arguments as key-value pairs "
                                        '(e.g. {"length": 24, "uppercase": true}).'
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
            The result, or a user-facing error message on
            failure.
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
            return f"Error: Failed to run script '{script_name}' in skill '{skill_name}'."

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
            The resource content (any type), or a user-facing error message on
            failure.
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
            return f"Error: Failed to read resource '{resource_name}' from skill '{skill_name}'."


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


@experimental(feature_id=ExperimentalFeature.SKILLS)
class SkillsSource(ABC):
    """Abstract base class for skill sources.

    A skill source discovers and returns :class:`Skill` instances from a
    particular origin.  The framework calls :meth:`get_skills` to obtain
    the available skills; implementations decide *where* and *how* skills
    are discovered (filesystem, memory, network, etc.).

    Subclass this to create custom skill sources.
    """

    @abstractmethod
    async def get_skills(self) -> list[Skill]:
        """Discover and return all skills from this source.

        Returns:
            A list of :class:`Skill` instances discovered by this source.
        """
        ...


class FileSkillsSource(SkillsSource):
    """Skill source that discovers skills from filesystem ``SKILL.md`` files.

    Recursively scans the configured *skill_paths* directories for
    ``SKILL.md`` files (up to 2 levels deep), parses their YAML frontmatter,
    and discovers associated resource and script files from spec-defined
    subdirectories.

    By default, resources are discovered from ``references/`` and ``assets/``
    subdirectories, and scripts from ``scripts/``, per the
    `agentskills.io specification
    <https://agentskills.io/specification>`_.  Use *resource_directories*
    and *script_directories* to customize which subdirectories are scanned.
    Pass ``"."`` to include files at the skill root level.

    Security: file-based metadata is XML-escaped before prompt injection,
    and resource reads are guarded against path traversal and symlink escape.
    Only use skills from trusted sources.

    Examples:
        Basic usage:

        .. code-block:: python

            source = FileSkillsSource(skill_paths="./skills")
            skills = await source.get_skills()

        With a script runner and custom directories:

        .. code-block:: python

            source = FileSkillsSource(
                skill_paths=["./skills", "./more-skills"],
                script_runner=my_runner,
                resource_directories=[".", "references", "assets"],
                script_directories=["scripts"],
            )
    """

    def __init__(
        self,
        skill_paths: str | Path | Sequence[str | Path],
        *,
        script_runner: SkillScriptRunner | None = None,
        resource_extensions: tuple[str, ...] | None = None,
        script_extensions: tuple[str, ...] | None = None,
        resource_directories: Sequence[str] | None = None,
        script_directories: Sequence[str] | None = None,
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
            resource_directories: Relative directory paths to scan for
                resource files within each skill directory.  Use ``"."``
                to include files at the skill root level.  Defaults to
                ``("references", "assets")`` per the
                `agentskills.io specification
                <https://agentskills.io/specification>`_.
            script_directories: Relative directory paths to scan for
                script files within each skill directory.  Use ``"."``
                to include files at the skill root level.  Defaults to
                ``("scripts",)`` per the
                `agentskills.io specification
                <https://agentskills.io/specification>`_.
        """
        if isinstance(skill_paths, (str, Path)):
            self._skill_paths: list[str] = [str(skill_paths)]
        else:
            self._skill_paths = [str(p) for p in skill_paths]

        self._script_runner = script_runner
        self._resource_extensions = resource_extensions or DEFAULT_RESOURCE_EXTENSIONS
        self._script_extensions = script_extensions or DEFAULT_SCRIPT_EXTENSIONS

        self._resource_directories: tuple[str, ...] = (
            tuple(FileSkillsSource._validate_and_normalize_directory_names(resource_directories))
            if resource_directories is not None
            else DEFAULT_RESOURCE_DIRECTORIES
        )
        self._script_directories: tuple[str, ...] = (
            tuple(FileSkillsSource._validate_and_normalize_directory_names(script_directories))
            if script_directories is not None
            else DEFAULT_SCRIPT_DIRECTORIES
        )

    async def get_skills(self) -> list[Skill]:
        """Discover and return all file-based skills from configured paths.

        Scans directories for ``SKILL.md`` files, parses their frontmatter,
        discovers resource and script files, and returns populated
        :class:`Skill` instances.

        Returns:
            A list of discovered file-based skills.
        """
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
            for rn in FileSkillsSource._discover_resource_files(
                skill_path, self._resource_extensions, self._resource_directories
            ):
                resource_full_path = FileSkillsSource._get_validated_resource_path(skill_path, rn)
                resources.append(_FileSkillResource(name=rn, full_path=resource_full_path))

            # Discover file-based scripts
            scripts: list[SkillScript] = []
            for sn in FileSkillsSource._discover_script_files(
                skill_path, self._script_extensions, self._script_directories
            ):
                script_full_path = os.path.normpath(os.path.join(skill_path, sn))  # noqa: ASYNC240
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

    @staticmethod
    def _validate_and_normalize_directory_names(
        directories: Sequence[str],
    ) -> list[str]:
        """Validate and normalize relative directory names.

        Ensures each entry is a safe relative path.  The ``"."`` root indicator
        is passed through unchanged.  Entries containing ``..`` segments or
        representing absolute paths are rejected with a warning and skipped.
        Empty or whitespace-only entries raise :class:`ValueError`.

        Args:
            directories: Sequence of relative directory names to validate.

        Returns:
            A list of validated, normalized directory names.

        Raises:
            ValueError: If any entry is empty or whitespace-only.
        """
        result: list[str] = []
        for directory in directories:
            if not directory or not directory.strip():
                raise ValueError("Directory names must not be empty or whitespace.")

            # Normalize separators: backslash → forward slash, strip leading ./ and trailing /
            normalized = PurePosixPath(directory.replace("\\", "/")).as_posix()

            # "." and "./" both normalize to "." — treat as root indicator
            if normalized == ROOT_DIRECTORY_INDICATOR:
                result.append(ROOT_DIRECTORY_INDICATOR)
                continue

            # Reject absolute paths (check both POSIX and Windows-style roots
            # so validation is consistent regardless of the host OS)
            if os.path.isabs(directory) or normalized.startswith("/") or re.match(r"^[A-Za-z]:[/\\]", directory):
                logger.warning(
                    "Skipping directory '%s': absolute paths are not allowed.",
                    directory,
                )
                continue

            # Reject paths containing ".." segments
            if any(segment == ".." for segment in normalized.split("/")):
                logger.warning(
                    "Skipping directory '%s': parent traversal ('..') is not allowed.",
                    directory,
                )
                continue

            result.append(normalized)
        return result

    @staticmethod
    def _discover_resource_files(
        skill_dir_path: str,
        extensions: tuple[str, ...] = DEFAULT_RESOURCE_EXTENSIONS,
        directories: tuple[str, ...] = DEFAULT_RESOURCE_DIRECTORIES,
    ) -> list[str]:
        """Scan configured subdirectories for resource files matching *extensions*.

        Scans each directory in *directories* within *skill_dir_path* for files
        whose extension is in *extensions*, excluding ``SKILL.md`` itself.
        Use ``"."`` in *directories* to include files at the skill root level.
        Each candidate is validated against path-traversal and symlink-escape
        checks; unsafe files are skipped with a warning.

        Args:
            skill_dir_path: Absolute path to the skill directory to scan.
            extensions: Tuple of allowed file extensions (e.g. ``(".md", ".json")``).
            directories: Relative subdirectory paths to scan for resources.

        Returns:
            Sorted relative resource paths (forward-slash-separated) for every
            discovered file that passes security checks.
        """
        skill_dir = Path(skill_dir_path).absolute()
        root_directory_path = str(skill_dir)
        resources: list[str] = []
        normalized_extensions = {e.lower() for e in extensions}
        seen_directories: set[str] = set()

        for directory in directories:
            is_root = directory == ROOT_DIRECTORY_INDICATOR
            target_dir = skill_dir if is_root else (skill_dir / directory)

            # Deduplicate after resolving to avoid scanning the same directory twice.
            # Use normcase for case-insensitive dedup on case-insensitive filesystems.
            resolved_target = str(Path(os.path.normpath(target_dir)).absolute())
            dedup_key = os.path.normcase(resolved_target)
            if dedup_key in seen_directories:
                continue
            seen_directories.add(dedup_key)

            if not target_dir.is_dir():
                continue

            # Directory-level containment and symlink checks for non-root directories
            if not is_root:
                if not FileSkillsSource._is_path_within_directory(resolved_target, root_directory_path):
                    logger.warning(
                        "Skipping resource directory '%s': resolves outside skill directory '%s'",
                        directory,
                        skill_dir_path,
                    )
                    continue

                if FileSkillsSource._has_symlink_in_path(resolved_target, root_directory_path):
                    logger.warning(
                        "Skipping resource directory '%s': symlink detected in path under skill directory '%s'",
                        directory,
                        skill_dir_path,
                    )
                    continue

            # Scan top-level files only (non-recursive) within this directory
            try:
                entries = list(target_dir.iterdir())
            except OSError:
                logger.warning(
                    "Failed to list resource directory '%s' in skill directory '%s'; skipping.",
                    directory,
                    skill_dir_path,
                )
                continue

            for resource_file in entries:
                if not resource_file.is_file():
                    continue

                if resource_file.name.upper() == SKILL_FILE_NAME.upper():
                    continue

                if resource_file.suffix.lower() not in normalized_extensions:
                    continue

                resource_full_path = str(Path(os.path.normpath(resource_file)).absolute())

                # Containment check: file must resolve within the target directory
                if not FileSkillsSource._is_path_within_directory(resource_full_path, resolved_target):
                    logger.warning(
                        "Skipping resource '%s': resolves outside target directory '%s'",
                        resource_file,
                        directory,
                    )
                    continue

                if FileSkillsSource._has_symlink_in_path(resource_full_path, root_directory_path):
                    logger.warning(
                        "Skipping resource '%s': symlink detected in path under skill directory '%s'",
                        resource_file,
                        skill_dir_path,
                    )
                    continue

                rel_path = resource_file.relative_to(skill_dir)
                resources.append(FileSkillsSource._normalize_resource_path(str(rel_path)))

        resources.sort()
        return resources

    @staticmethod
    def _discover_script_files(
        skill_dir_path: str,
        extensions: tuple[str, ...] = DEFAULT_SCRIPT_EXTENSIONS,
        directories: tuple[str, ...] = DEFAULT_SCRIPT_DIRECTORIES,
    ) -> list[str]:
        """Scan configured subdirectories for script files matching *extensions*.

        Scans each directory in *directories* within *skill_dir_path* for files
        whose extension is in *extensions*.  Use ``"."`` in *directories* to
        include files at the skill root level.  Each candidate is validated
        against path-traversal and symlink-escape checks; unsafe files are
        skipped with a warning.

        Args:
            skill_dir_path: Absolute path to the skill directory to scan.
            extensions: Tuple of allowed script extensions (e.g. ``(".py",)``).
            directories: Relative subdirectory paths to scan for scripts.

        Returns:
            Sorted relative script paths (forward-slash-separated) for every
            discovered file that passes security checks.
        """
        skill_dir = Path(skill_dir_path).absolute()
        root_directory_path = str(skill_dir)
        scripts: list[str] = []
        normalized_extensions = {e.lower() for e in extensions}
        seen_directories: set[str] = set()

        for directory in directories:
            is_root = directory == ROOT_DIRECTORY_INDICATOR
            target_dir = skill_dir if is_root else (skill_dir / directory)

            # Deduplicate after resolving to avoid scanning the same directory twice.
            # Use normcase for case-insensitive dedup on case-insensitive filesystems.
            resolved_target = str(Path(os.path.normpath(target_dir)).absolute())
            dedup_key = os.path.normcase(resolved_target)
            if dedup_key in seen_directories:
                continue
            seen_directories.add(dedup_key)

            if not target_dir.is_dir():
                continue

            # Directory-level containment and symlink checks for non-root directories
            if not is_root:
                if not FileSkillsSource._is_path_within_directory(resolved_target, root_directory_path):
                    logger.warning(
                        "Skipping script directory '%s': resolves outside skill directory '%s'",
                        directory,
                        skill_dir_path,
                    )
                    continue

                if FileSkillsSource._has_symlink_in_path(resolved_target, root_directory_path):
                    logger.warning(
                        "Skipping script directory '%s': symlink detected in path under skill directory '%s'",
                        directory,
                        skill_dir_path,
                    )
                    continue

            # Scan top-level files only (non-recursive) within this directory
            try:
                entries = list(target_dir.iterdir())
            except OSError:
                logger.warning(
                    "Failed to list script directory '%s' in skill directory '%s'; skipping.",
                    directory,
                    skill_dir_path,
                )
                continue

            for script_file in entries:
                if not script_file.is_file():
                    continue

                if script_file.suffix.lower() not in normalized_extensions:
                    continue

                script_full_path = str(Path(os.path.normpath(script_file)).absolute())

                # Containment check: file must resolve within the target directory
                if not FileSkillsSource._is_path_within_directory(script_full_path, resolved_target):
                    logger.warning(
                        "Skipping script '%s': resolves outside target directory '%s'",
                        script_file,
                        directory,
                    )
                    continue

                if FileSkillsSource._has_symlink_in_path(script_full_path, root_directory_path):
                    logger.warning(
                        "Skipping script '%s': symlink detected in path under skill directory '%s'",
                        script_file,
                        skill_dir_path,
                    )
                    continue

                rel_path = script_file.relative_to(skill_dir)
                scripts.append(FileSkillsSource._normalize_resource_path(str(rel_path)))

        scripts.sort()
        return scripts

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

        Recursively searches each root path up to :data:`MAX_SEARCH_DEPTH`.

        Args:
            skill_paths: Root directory paths to search.

        Returns:
            Absolute paths to directories containing ``SKILL.md``.
        """
        discovered: list[str] = []

        def _search(directory: str, current_depth: int) -> None:
            dir_path = Path(directory)
            if (dir_path / SKILL_FILE_NAME).is_file():
                discovered.append(str(dir_path.absolute()))

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
            skills = await source.get_skills()
    """

    def __init__(self, skills: Sequence[Skill]) -> None:
        """Initialize an InMemorySkillsSource.

        Args:
            skills: :class:`Skill` instances to serve from this source.
        """
        self._skills = list(skills)

    async def get_skills(self) -> list[Skill]:
        """Return the stored skills.

        Returns:
            A list of :class:`Skill` instances.
        """
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

    async def get_skills(self) -> list[Skill]:
        """Delegate to the inner source.

        Subclasses should override this to intercept the results.

        Returns:
            Skills from the inner source.
        """
        return await self._inner_source.get_skills()


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
            skills = await deduped.get_skills()
    """

    def __init__(self, inner_source: SkillsSource) -> None:
        """Initialize a DeduplicatingSkillsSource.

        Args:
            inner_source: The source whose results will be deduplicated.
        """
        super().__init__(inner_source)

    async def get_skills(self) -> list[Skill]:
        """Return deduplicated skills (first-one-wins by name).

        Returns:
            A list of :class:`Skill` instances with duplicate names removed.
        """
        skills = await self._inner_source.get_skills()
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
    result.  The predicate receives each :class:`Skill` and should return
    a boolean.

    Examples:
        .. code-block:: python

            filtered = FilteringSkillsSource(
                inner_source=my_source,
                predicate=lambda s: s.frontmatter.name != "internal",
            )
            skills = await filtered.get_skills()
    """

    def __init__(
        self,
        inner_source: SkillsSource,
        predicate: Callable[[Skill], bool],
    ) -> None:
        """Initialize a FilteringSkillsSource.

        Args:
            inner_source: The source to filter.
            predicate: A callable that receives a :class:`Skill` and returns
                ``True`` to keep it or ``False`` to exclude it.
        """
        super().__init__(inner_source)
        self._predicate = predicate

    async def get_skills(self) -> list[Skill]:
        """Return only skills that match the predicate.

        Returns:
            A filtered list of :class:`Skill` instances.
        """
        skills = await self._inner_source.get_skills()
        return [s for s in skills if self._predicate(s)]


class AggregatingSkillsSource(SkillsSource):
    """Skill source that composes multiple sources into one."""

    def __init__(self, sources: Sequence[SkillsSource]) -> None:
        self._sources = list(sources)

    async def get_skills(self) -> list[Skill]:
        result: list[Skill] = []
        for source in self._sources:
            skills = await source.get_skills()
            result.extend(skills)
        return result


# endregion
