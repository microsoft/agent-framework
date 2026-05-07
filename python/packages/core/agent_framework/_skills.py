# Copyright (c) Microsoft. All rights reserved.

"""Agent Skills provider, models, and discovery utilities.

Defines the core data model classes for the agent skills system:

- **Skills:** :class:`Skill` (abstract base), :class:`InlineSkill` (code-defined),
  and :class:`FileSkill` (filesystem-backed).
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
    async def run(self, skill: Skill, args: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Run this script.

        Args:
            skill: The skill that owns this script.
            args: Optional keyword arguments for the script, provided by the
                agent/LLM.
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

    async def run(self, skill: Skill, args: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Run the script by invoking the callable in-process.

        Args:
            skill: The skill that owns this script.
            args: Optional keyword arguments for the script, provided by the
                agent/LLM.
            **kwargs: Runtime keyword arguments forwarded only to script
                functions that accept ``**kwargs``.

        Returns:
            The script execution result.
        """
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

    async def run(self, skill: Skill, args: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Run the script by delegating to the configured runner.

        Args:
            skill: The skill that owns this script.  Must be a
                :class:`FileSkill`.
            args: Optional keyword arguments for the script.
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
    :class:`FileSkill` (filesystem-backed) and :class:`InlineSkill`
    (code-defined).

    Skill metadata follows the
    `Agent Skills specification <https://agentskills.io/>`_.

    Attributes:
        name: Skill name (lowercase letters, numbers, hyphens only).
        description: Human-readable description of the skill.
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
    ) -> None:
        """Initialize a Skill.

        Validates the skill name and description against specification rules.

        Args:
            name: Skill name (lowercase letters, numbers, hyphens only;
                max 64 characters; no leading/trailing/consecutive hyphens).
            description: Human-readable description of the skill
                (≤1024 characters).

        Raises:
            ValueError: If the name or description is invalid.
        """
        _validate_skill_name(name)
        _validate_skill_description(name, description)

        self.name = name
        self.description = description

    @property
    @abstractmethod
    def content(self) -> str:
        """The full skill content.

        For file-based skills this is the raw SKILL.md file content,
        optionally augmented with a synthesized scripts block when scripts
        are present.  For code-defined skills this is a synthesized XML
        document containing name, description, and body (instructions,
        resources, scripts).
        """
        ...

    @property
    def resources(self) -> list[SkillResource]:
        """Resources associated with this skill.

        The default implementation returns an empty list.
        Override this property in derived classes to provide skill-specific
        resources.
        """
        return []

    @property
    def scripts(self) -> list[SkillScript]:
        """Scripts associated with this skill.

        The default implementation returns an empty list.
        Override this property in derived classes to provide skill-specific
        scripts.
        """
        return []


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


@experimental(feature_id=ExperimentalFeature.SKILLS)
class InlineSkill(Skill):
    """A skill defined entirely in code with resources and scripts.

    All resources and scripts should be configured before the skill is
    registered with a :class:`SkillsProvider`.

    Attributes:
        name: Skill name (lowercase letters, numbers, hyphens only).
        description: Human-readable description of the skill.
        instructions: The skill instructions text.

    Examples:
        With the decorator:

        .. code-block:: python

            skill = InlineSkill(
                name="db-skill",
                description="Database operations",
                instructions="Use this skill for DB tasks.",
            )


            @skill.resource
            def get_schema() -> str:
                return "CREATE TABLE ..."
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        instructions: str,
        resources: Sequence[SkillResource] | None = None,
        scripts: Sequence[SkillScript] | None = None,
    ) -> None:
        """Initialize an InlineSkill.

        Args:
            name: Skill name (lowercase letters, numbers, hyphens only).
            description: Human-readable description of the skill (≤1024 chars).
            instructions: The skill instructions text.
            resources: Pre-built resources to attach to this skill.
            scripts: Pre-built scripts to attach to this skill.
        """
        super().__init__(name=name, description=description)

        self.instructions = instructions
        self._resources: list[SkillResource] = list(resources) if resources is not None else []
        self._scripts: list[SkillScript] = list(scripts) if scripts is not None else []
        self._cached_content: str | None = None

    @property
    def content(self) -> str:
        """Synthesized XML content with name, description, instructions, resources, and scripts.

        The result is cached after the first access.  Adding resources or
        scripts after the first access will not be reflected.
        """
        if self._cached_content is not None:
            return self._cached_content

        result = (
            f"<name>{xml_escape(self.name)}</name>\n"
            f"<description>{xml_escape(self.description)}</description>\n"
            "\n"
            "<instructions>\n"
            f"{self.instructions}\n"
            "</instructions>"
        )

        if self._resources:
            resource_lines = "\n".join(self._create_resource_element(r) for r in self._resources)
            result += f"\n\n<resources>\n{resource_lines}\n</resources>"

        if self._scripts:
            script_lines = "\n".join(_create_script_element(s) for s in self._scripts)
            result += f"\n\n<scripts>\n{script_lines}\n</scripts>"

        self._cached_content = result
        return result

    @property
    def resources(self) -> list[SkillResource]:
        """Mutable list of :class:`SkillResource` instances."""
        return self._resources

    @property
    def scripts(self) -> list[SkillScript]:
        """Mutable list of :class:`SkillScript` instances."""
        return self._scripts

    @staticmethod
    def _create_resource_element(resource: SkillResource) -> str:
        """Create a self-closing ``<resource …/>`` XML element from an :class:`SkillResource`.

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
            description: Resource description override.  Defaults to the
                function's docstring (via :func:`inspect.getdoc`).

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
            resource_description = description or (inspect.getdoc(f) or None)
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
            description: Script description override.  Defaults to the
                function's docstring (via :func:`inspect.getdoc`).

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
            script_description = description or (inspect.getdoc(f) or None)
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


@experimental(feature_id=ExperimentalFeature.SKILLS)
class FileSkill(Skill):
    """A :class:`Skill` discovered from a filesystem directory backed by a SKILL.md file.

    Attributes:
        name: Skill name (lowercase letters, numbers, hyphens only).
        description: Human-readable description of the skill.
        path: Absolute path to the directory containing this skill.
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        content: str,
        path: str,
        resources: Sequence[SkillResource] | None = None,
        scripts: Sequence[SkillScript] | None = None,
    ) -> None:
        """Initialize a FileSkill.

        Args:
            name: Skill name (lowercase letters, numbers, hyphens only).
            description: Human-readable description of the skill (≤1024 chars).
            content: The full raw SKILL.md file content including YAML frontmatter.
            path: Absolute path to the skill directory on disk.
            resources: Resources discovered for this skill.
            scripts: Scripts discovered for this skill.
        """
        super().__init__(name=name, description=description)

        self._content = content
        self.path = path
        self._resources: list[SkillResource] = list(resources) if resources is not None else []
        self._scripts: list[SkillScript] = list(scripts) if scripts is not None else []

    @property
    def content(self) -> str:
        """The skill content provided at construction time."""
        return self._content

    @property
    def resources(self) -> list[SkillResource]:
        """Resources discovered for this skill."""
        return self._resources

    @property
    def scripts(self) -> list[SkillScript]:
        """Scripts discovered for this skill."""
        return self._scripts


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

    def __call__(self, skill: FileSkill, script: FileSkillScript, args: dict[str, Any] | None = None) -> Any:
        """Run a skill script.

        The :class:`SkillsProvider` resolves skill and script names
        before calling this method, so implementations receive fully
        resolved objects.

        Args:
            skill: The file-based skill that owns the script.
            script: The file-based script to run.
            args: Optional keyword arguments for the script.

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

# region Patterns and prompt template

# Matches YAML frontmatter delimited by "---" lines.
# The \uFEFF? prefix allows an optional UTF-8 BOM.
FRONTMATTER_RE = re.compile(
    r"\A\uFEFF?---\s*$(.+?)^---\s*$",
    re.MULTILINE | re.DOTALL,
)

# Matches YAML "key: value" lines. Group 1 = key, Group 2 = quoted value,
# Group 3 = unquoted value.
YAML_KV_RE = re.compile(
    r"^\s*(\w+)\s*:\s*(?:[\"'](.+?)[\"']|(.+?))\s*$",
    re.MULTILINE,
)

# Validates skill names: lowercase letters, numbers, hyphens only;
# must not start or end with a hyphen, and must not contain consecutive hyphens.
VALID_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9]*-[a-z0-9])*[a-z0-9]*$")

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
                    predicate=lambda s: s.name != "internal",
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
                generated skills list. If the provider includes file-based script
                execution instructions, the template must also contain
                ``{runner_instructions}``. If the provider includes resource-reading
                instructions, the template must also contain
                ``{resource_instructions}``. Omitting any placeholder required by
                the resolved skills configuration can raise :class:`ValueError` at
                runtime. Uses a built-in template when ``None``.
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
        include_script_runner_instructions: bool = False,
        include_resource_instructions: bool = False,
    ) -> str | None:
        """Create the system-prompt text that advertises available skills.

        Generates an XML list of ``<skill>`` elements (sorted by name) and
        inserts it into *prompt_template* at the ``{skills}`` placeholder.
        When *include_script_runner_instructions* is ``True``, executor-provided
        instructions are inserted at the ``{runner_instructions}`` placeholder.
        When *include_resource_instructions* is ``True``, resource-reading
        instructions are inserted at the ``{resource_instructions}`` placeholder.

        Args:
            prompt_template: Custom template string with ``{skills}`` and
                optional ``{runner_instructions}`` and ``{resource_instructions}``
                placeholders, or ``None`` to use the built-in default.
            skills: Registered skills.
            include_script_runner_instructions: When ``True``, include
                script-runner instructions in the generated prompt.
                Defaults to ``False``.
            include_resource_instructions: When ``True``, include
                resource-reading instructions in the generated prompt.
                Defaults to ``False``.

        Returns:
            The formatted instruction string, or ``None`` when *skills* is empty.

        Raises:
            ValueError: If *prompt_template* is not a valid format string
                (e.g. missing ``{skills}`` placeholder).
        """
        runner_instructions = SCRIPT_RUNNER_INSTRUCTIONS if include_script_runner_instructions else None
        resource_instructions = RESOURCE_INSTRUCTIONS if include_resource_instructions else None
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
            if runner_instructions and "__EXEC_PROBE__" not in result:
                raise ValueError(
                    "The provided instruction_template must contain an '{runner_instructions}' placeholder "  # noqa: RUF027
                    "when a script runner is configured."
                )
            if resource_instructions and "__RES_PROBE__" not in result:
                raise ValueError(
                    "The provided instruction_template must contain a '{resource_instructions}' placeholder "  # noqa: RUF027
                    "when skills have resources."
                )
            template = prompt_template

        if not skills:
            return None

        lines: list[str] = []
        # Sort by name for deterministic output
        for skill in sorted(skills, key=lambda s: s.name):
            lines.append("  <skill>")
            lines.append(f"    <name>{xml_escape(skill.name)}</name>")
            lines.append(f"    <description>{xml_escape(skill.description)}</description>")
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

        has_scripts = any(s.scripts for s in skills)
        has_resources = any(s.resources for s in skills)

        instructions = self._create_instructions(
            prompt_template=self._instruction_template,
            skills=skills,
            include_script_runner_instructions=has_scripts,
            include_resource_instructions=has_resources,
        )

        tools = self._create_tools(
            skills=skills,
            include_script_runner_tool=has_scripts,
            include_resource_tool=has_resources,
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
        include_script_runner_tool: bool,
        include_resource_tool: bool,
        require_script_approval: bool = False,
    ) -> list[FunctionTool]:
        """Create the tool definitions for skill interaction.

        Always includes ``load_skill``. Conditionally includes
        ``read_skill_resource`` (when *include_resource_tool* is ``True``)
        and ``run_skill_script`` (when *include_script_runner_tool* is
        ``True``).

        Args:
            skills: The skills to bind to tool handlers.
            include_script_runner_tool: Whether to include the
                ``run_skill_script`` tool in the returned list.
            include_resource_tool: Whether to include the
                ``read_skill_resource`` tool in the returned list.
            require_script_approval: When ``True``, the
                ``run_skill_script`` tool pauses for user approval
                before each invocation.

        Returns:
            A list of :class:`FunctionTool` instances.
        """
        tools = [
            FunctionTool(
                name="load_skill",
                description="Loads the full instructions for a specific skill.",
                func=lambda skill_name: self._load_skill(skills, skill_name),  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType]
                input_model={
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string", "description": "The name of the skill to load."},
                    },
                    "required": ["skill_name"],
                },
            ),
        ]

        if include_resource_tool:

            async def _read_resource(skill_name: str, resource_name: str, **kwargs: Any) -> Any:
                return await self._read_skill_resource(skills, skill_name, resource_name, **kwargs)

            tools.append(
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
                )
            )

        if include_script_runner_tool:

            async def _run_script(
                skill_name: str, script_name: str, args: dict[str, Any] | None = None, **kwargs: Any
            ) -> Any:
                return await self._run_skill_script(skills, skill_name, script_name, args, **kwargs)

            tools.append(
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
                                "type": ["object", "null"],
                                "additionalProperties": True,
                                "default": None,
                                "description": (
                                    "Arguments to pass to the script as key-value pairs. "
                                    "Use parameter names as keys without leading dashes "
                                    '(e.g. {"length": 24, "uppercase": true}). '
                                    "How these values are mapped to the underlying script "
                                    "is determined by the script implementation or configured runner."
                                ),
                            },
                        },
                        "required": ["skill_name", "script_name"],
                    },
                )
            )

        return tools

    @staticmethod
    def _find_skill(skills: Sequence[Skill], name: str) -> Skill | None:
        """Find a skill by name (case-insensitive linear scan)."""
        name_lower = name.lower()
        return next((s for s in skills if s.name.lower() == name_lower), None)

    def _load_skill(self, skills: Sequence[Skill], skill_name: str) -> str:
        """Return the full content for the named skill.

        Delegates to the skill's :attr:`~Skill.content` property, which
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

        return skill.content

    async def _run_skill_script(
        self,
        skills: Sequence[Skill],
        skill_name: str,
        script_name: str,
        args: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run a named script from a skill.

        Resolves the skill and script by name, then delegates execution
        to :meth:`SkillScript.run`.

        Args:
            skills: The skills to look up the skill from.
            skill_name: The name of the owning skill.
            script_name: The script name to look up (case-insensitive).
            args: Optional keyword arguments for the script, provided by the
                agent/LLM.  These are mapped to the function's declared
                parameters.
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

        script = next((s for s in skill.scripts if s.name.lower() == script_name.lower()), None)
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

        # Find resource by name (case-insensitive)
        resource_name_lower = resource_name.lower()
        for resource in skill.resources:
            if resource.name.lower() == resource_name_lower:
                break
        else:
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
    and discovers associated resource and script files from subdirectories.

    Security: file-based metadata is XML-escaped before prompt injection,
    and resource reads are guarded against path traversal and symlink escape.
    Only use skills from trusted sources.

    Examples:
        Basic usage:

        .. code-block:: python

            source = FileSkillsSource(skill_paths="./skills")
            skills = await source.get_skills()

        With a script runner and custom extensions:

        .. code-block:: python

            source = FileSkillsSource(
                skill_paths=["./skills", "./more-skills"],
                script_runner=my_runner,
                script_extensions=(".py", ".sh"),
            )
    """

    def __init__(
        self,
        skill_paths: str | Path | Sequence[str | Path],
        *,
        script_runner: SkillScriptRunner | None = None,
        resource_extensions: tuple[str, ...] | None = None,
        script_extensions: tuple[str, ...] | None = None,
    ) -> None:
        """Initialize a FileSkillsSource.

        Args:
            skill_paths: One or more directory paths to search for file-based
                skills.  Each path may point to an individual skill folder
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
        """
        if isinstance(skill_paths, (str, Path)):
            self._skill_paths: list[str] = [str(skill_paths)]
        else:
            self._skill_paths = [str(p) for p in skill_paths]

        self._script_runner = script_runner
        self._resource_extensions = resource_extensions or DEFAULT_RESOURCE_EXTENSIONS
        self._script_extensions = script_extensions or DEFAULT_SCRIPT_EXTENSIONS

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

            name, description, content = parsed

            if name in skills:
                logger.warning(
                    "Duplicate skill name '%s': skill from '%s' skipped in favor of existing skill",
                    name,
                    skill_path,
                )
                continue

            file_skill = FileSkill(
                name=name,
                description=description,
                content=content,
                path=skill_path,
            )

            # Discover and attach file-based resources
            for rn in FileSkillsSource._discover_resource_files(skill_path, self._resource_extensions):
                resource_full_path = FileSkillsSource._get_validated_resource_path(skill_path, rn)
                file_skill.resources.append(_FileSkillResource(name=rn, full_path=resource_full_path))

            # Discover and attach file-based scripts as SkillScript instances
            for sn in FileSkillsSource._discover_script_files(skill_path, self._script_extensions):
                script_full_path = os.path.normpath(os.path.join(skill_path, sn))  # noqa: ASYNC240
                file_skill.scripts.append(
                    FileSkillScript(name=sn, full_path=script_full_path, runner=self._script_runner)
                )

            skills[file_skill.name] = file_skill
            logger.info("Loaded skill: %s", file_skill.name)

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
    def _discover_resource_files(
        skill_dir_path: str,
        extensions: tuple[str, ...] = DEFAULT_RESOURCE_EXTENSIONS,
    ) -> list[str]:
        """Scan a skill directory for resource files matching *extensions*.

        Recursively walks *skill_dir_path* and collects files whose extension
        is in *extensions*, excluding ``SKILL.md`` itself.  Each candidate is
        validated against path-traversal and symlink-escape checks; unsafe
        files are skipped with a warning.

        Args:
            skill_dir_path: Absolute path to the skill directory to scan.
            extensions: Tuple of allowed file extensions (e.g. ``(".md", ".json")``).

        Returns:
            Relative resource paths (forward-slash-separated) for every
            discovered file that passes security checks.
        """
        skill_dir = Path(skill_dir_path).absolute()
        root_directory_path = str(skill_dir)
        resources: list[str] = []
        normalized_extensions = {e.lower() for e in extensions}

        for resource_file in skill_dir.rglob("*"):
            if not resource_file.is_file():
                continue

            if resource_file.name.upper() == SKILL_FILE_NAME.upper():
                continue

            if resource_file.suffix.lower() not in normalized_extensions:
                continue

            resource_full_path = str(Path(os.path.normpath(resource_file)).absolute())

            if not FileSkillsSource._is_path_within_directory(resource_full_path, root_directory_path):
                logger.warning(
                    "Skipping resource '%s': resolves outside skill directory '%s'",
                    resource_file,
                    skill_dir_path,
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

        return resources

    @staticmethod
    def _discover_script_files(
        skill_dir_path: str,
        extensions: tuple[str, ...] = DEFAULT_SCRIPT_EXTENSIONS,
    ) -> list[str]:
        """Scan a skill directory for script files matching *extensions*.

        Recursively walks *skill_dir_path* and collects files whose extension
        is in *extensions*.  Each candidate is validated against path-traversal
        and symlink-escape checks; unsafe files are skipped with a warning.

        Args:
            skill_dir_path: Absolute path to the skill directory to scan.
            extensions: Tuple of allowed script extensions (e.g. ``(".py",)``).

        Returns:
            Relative script paths (forward-slash-separated) for every
            discovered file that passes security checks.
        """
        skill_dir = Path(skill_dir_path).absolute()
        root_directory_path = str(skill_dir)
        scripts: list[str] = []
        normalized_extensions = {e.lower() for e in extensions}

        for script_file in skill_dir.rglob("*"):
            if not script_file.is_file():
                continue

            if script_file.suffix.lower() not in normalized_extensions:
                continue

            script_full_path = str(Path(os.path.normpath(script_file)).absolute())

            if not FileSkillsSource._is_path_within_directory(script_full_path, root_directory_path):
                logger.warning(
                    "Skipping script '%s': resolves outside skill directory '%s'",
                    script_file,
                    skill_dir_path,
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
    ) -> str | None:
        """Validate a skill's name and description against naming rules.

        Enforces length limits, character-set restrictions, and non-emptiness
        for both file-based and code-defined skills.

        Args:
            name: Skill name to validate.
            description: Skill description to validate.
            source: Human-readable label for diagnostics (e.g. a file path
                or ``"code skill"``).

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

        return None

    @staticmethod
    def _extract_frontmatter(
        content: str,
        skill_file_path: str,
    ) -> tuple[str, str] | None:
        """Extract and validate YAML frontmatter from a SKILL.md file.

        Parses the ``---``-delimited frontmatter block for ``name`` and
        ``description`` fields.

        Args:
            content: Raw text content of the SKILL.md file.
            skill_file_path: Path to the file (used in diagnostic messages only).

        Returns:
            A ``(name, description)`` tuple on success, or ``None`` if the
            frontmatter is missing, malformed, or fails validation.
        """
        match = FRONTMATTER_RE.search(content)
        if not match:
            logger.error("SKILL.md at '%s' does not contain valid YAML frontmatter delimited by '---'", skill_file_path)
            return None

        yaml_content = match.group(1).strip()
        name: str | None = None
        description: str | None = None

        for kv_match in YAML_KV_RE.finditer(yaml_content):
            key = kv_match.group(1)
            value = kv_match.group(2) if kv_match.group(2) is not None else kv_match.group(3)

            if key.lower() == "name":
                name = value
            elif key.lower() == "description":
                description = value

        error = FileSkillsSource._validate_skill_metadata(name, description, skill_file_path)
        if error:
            logger.error(error)
            return None

        # name and description are guaranteed non-None after validation
        return name, description  # type: ignore[return-value]

    @staticmethod
    def _read_and_parse_skill_file(
        skill_dir_path: str,
    ) -> tuple[str, str, str] | None:
        """Read and parse the SKILL.md file in *skill_dir_path*.

        Args:
            skill_dir_path: Absolute path to the directory containing ``SKILL.md``.

        Returns:
            A ``(name, description, content)`` tuple where *content* is the
            full raw file text, or ``None`` if the file cannot be read or
            its frontmatter is invalid.
        """
        skill_file = Path(skill_dir_path) / SKILL_FILE_NAME

        try:
            content = skill_file.read_text(encoding="utf-8")
        except OSError:
            logger.error("Failed to read SKILL.md at '%s'", skill_file)
            return None

        result = FileSkillsSource._extract_frontmatter(content, str(skill_file))
        if result is None:
            return None

        name, description = result

        dir_name = Path(skill_dir_path).name
        if name != dir_name:
            logger.error(
                "SKILL.md at '%s' has frontmatter name '%s' that does not match the directory name '%s'; skipping.",
                skill_file,
                name,
                dir_name,
            )
            return None

        return name, description, content

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
            key = skill.name.lower()
            if key in seen:
                logger.warning(
                    "Duplicate skill name '%s': skill skipped in favor of existing skill '%s'",
                    skill.name,
                    seen[key].name,
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
                predicate=lambda s: s.name != "internal",
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
