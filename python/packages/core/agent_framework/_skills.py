# Copyright (c) Microsoft. All rights reserved.

"""Agent Skills provider, models, and discovery utilities.

Defines :class:`SkillResource` and :class:`Skill`, the core data model classes
for the agent skills system, along with :class:`SkillsProvider` which implements
the progressive-disclosure pattern from the
`Agent Skills specification <https://agentskills.io/>`_:

1. **Advertise** — skill names and descriptions are injected into the system prompt.
2. **Load** — the full SKILL.md body is returned via the ``load_skill`` tool.
3. **Read resources** — supplementary content is returned on demand via
   the ``read_skill_resource`` tool.

Skills can originate from two sources:

- **File-based** — discovered by scanning configured directories for ``SKILL.md`` files.
- **Code-defined** — created as :class:`Skill` instances in Python code,
  with optional callable resources attached via the ``@skill.resource`` decorator.

**Security:** file-based skill metadata is XML-escaped before prompt injection, and
file-based resource reads are guarded against path traversal and symlink escape.
Only use skills from trusted sources.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import re
from collections.abc import Callable, Sequence
from html import escape as xml_escape
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, ClassVar, Final, Protocol, runtime_checkable

from ._sessions import BaseContextProvider
from ._tools import FunctionTool

if TYPE_CHECKING:
    from ._agents import SupportsAgentRun
    from ._sessions import AgentSession, SessionContext

logger = logging.getLogger(__name__)

# region Models


class SkillResource:
    """A named piece of supplementary content attached to a skill.

    .. warning:: Experimental

        This API is experimental and subject to change or removal
        in future versions without notice.

    A resource provides data that an agent can retrieve on demand.  It holds
    either a static ``content`` string or a ``function`` that produces content
    dynamically (sync or async).  Exactly one must be provided.

    Attributes:
        name: Resource identifier.
        description: Optional human-readable summary, or ``None``.
        content: Static content string, or ``None`` if backed by a callable.
        function: Callable that returns content, or ``None`` if backed by static content.

    Examples:
        Static resource:

        .. code-block:: python

            SkillResource(name="reference", content="Static docs here...")

        Callable resource:

        .. code-block:: python

            SkillResource(name="schema", function=get_schema_func)
    """

    def __init__(
        self,
        *,
        name: str,
        description: str | None = None,
        content: str | None = None,
        function: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize a SkillResource.

        Args:
            name: Identifier for this resource (e.g. ``"reference"``, ``"get-schema"``).
            description: Optional human-readable summary shown when advertising the resource.
            content: Static content string.  Mutually exclusive with *function*.
            function: Callable (sync or async) that returns content on demand.
                May return any type; the value is passed through as-is.
                Mutually exclusive with *content*.
        """
        if not name or not name.strip():
            raise ValueError("Resource name cannot be empty.")
        if content is None and function is None:
            raise ValueError(f"Resource '{name}' must have either content or function.")
        if content is not None and function is not None:
            raise ValueError(f"Resource '{name}' must have either content or function, not both.")

        self.name = name
        self.description = description
        self.content = content
        self.function = function

        # Precompute whether the function accepts **kwargs to avoid
        # repeated inspect.signature() calls on every invocation.
        self._accepts_kwargs: bool = False
        if function is not None:
            sig = inspect.signature(function)
            self._accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


class SkillScript:
    """An executable script attached to a skill.

    .. warning:: Experimental

        This API is experimental and subject to change or removal
        in future versions without notice.

    A script represents executable code that an agent can run.  It holds
    either an inline ``function`` callable (code-defined scripts) or
    a ``path`` to a script file on disk (file-based scripts).
    Exactly one must be provided.

    When ``function`` is set the script is treated as **code-based**
    and the function is invoked directly in-process.  When ``path`` is
    set the script is treated as **file-based** and delegated to the
    configured :class:`SkillScriptRunner`.

    Attributes:
        name: Script identifier.
        description: Optional human-readable summary, or ``None``.
        function: Callable that implements the script, or ``None``.
        path: Relative path to the script file from the skill directory, or
            ``None`` for code-defined scripts.

    Examples:
        Code-defined script:

        .. code-block:: python

            SkillScript(name="analyze", function=analyze_data, description="Run analysis")

        File-based script (discovered from disk):

        .. code-block:: python

            SkillScript(name="process.py", path="scripts/process.py")
    """

    def __init__(
        self,
        *,
        name: str,
        description: str | None = None,
        function: Callable[..., Any] | None = None,
        path: str | None = None,
    ) -> None:
        """Initialize a SkillScript.

        Args:
            name: Identifier for this script (e.g. ``"analyze"``, ``"process.py"``).
            description: Optional human-readable summary.
            function: Callable (sync or async) that implements the script.
                Set for code-defined scripts; ``None`` for file-based scripts.
                Mutually exclusive with *path*.
            path: Relative path to the script file from the skill directory.
                Set automatically for file-based scripts discovered from disk;
                ``None`` for code-defined scripts.
                Mutually exclusive with *function*.
        """
        if not name or not name.strip():
            raise ValueError("Script name cannot be empty.")
        if function is None and path is None:
            raise ValueError(f"Script '{name}' must have either function or path.")
        if function is not None and path is not None:
            raise ValueError(f"Script '{name}' must have either function or path, not both.")

        self.name = name
        self.description = description
        self.function = function
        self.path = path
        self._parameters_schema: dict[str, Any] | None = None
        self._parameters_schema_resolved: bool = False

        # Precompute whether the function accepts **kwargs to avoid
        # repeated inspect.signature() calls on every invocation.
        self._accepts_kwargs: bool = False
        if function is not None:
            sig = inspect.signature(function)
            self._accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())

    @property
    def parameters_schema(self) -> dict[str, Any] | None:
        """JSON Schema describing the script's parameters.

        .. warning:: Experimental

            This API is experimental and subject to change or removal
            in future versions without notice.

        Lazily generated from the callable's signature on first access.
        Returns ``None`` for file-based scripts or functions with no
        introspectable parameters.
        """
        if not self._parameters_schema_resolved and self.function is not None:
            tool = FunctionTool(name=self.function.__name__, func=self.function)
            schema = tool.parameters()
            self._parameters_schema = schema if schema and schema.get("properties") else None
            self._parameters_schema_resolved = True
        return self._parameters_schema


class Skill:
    """A skill definition with optional resources.

    .. warning:: Experimental

        This API is experimental and subject to change or removal
        in future versions without notice.

    A skill bundles a set of instructions (``content``) with metadata and
    zero or more :class:`SkillResource` and :class:`SkillScript` instances.
    Resources and scripts can be supplied at construction time or added later
    via the :meth:`resource` and :meth:`script` decorators.

    Attributes:
        name: Skill name (lowercase letters, numbers, hyphens only).
        description: Human-readable description of the skill.
        content: The skill instructions body.
        resources: Mutable list of :class:`SkillResource` instances.
        scripts: Mutable list of :class:`SkillScript` instances.
        path: Absolute path to the skill directory on disk, or ``None``
            for code-defined skills.

    Examples:
        Direct construction:

        .. code-block:: python

            skill = Skill(
                name="my-skill",
                description="A skill example",
                content="Use this skill for ...",
                resources=[SkillResource(name="ref", content="...")],
            )

        With dynamic resources:

        .. code-block:: python

            skill = Skill(
                name="db-skill",
                description="Database operations",
                content="Use this skill for DB tasks.",
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
        content: str,
        resources: list[SkillResource] | None = None,
        scripts: list[SkillScript] | None = None,
        path: str | None = None,
    ) -> None:
        """Initialize a Skill.

        Args:
            name: Skill name (lowercase letters, numbers, hyphens only).
            description: Human-readable description of the skill (≤1024 chars).
            content: The skill instructions body.
            resources: Pre-built resources to attach to this skill.
            scripts: Pre-built scripts to attach to this skill.
            path: Absolute path to the skill directory on disk.  Set automatically
                for file-based skills; leave as ``None`` for code-defined skills.
        """
        if not name or not name.strip():
            raise ValueError("Skill name cannot be empty.")
        if not description or not description.strip():
            raise ValueError("Skill description cannot be empty.")

        self.name = name
        self.description = description
        self.content = content
        self.resources: list[SkillResource] = resources if resources is not None else []
        self.scripts: list[SkillScript] = scripts if scripts is not None else []
        self.path = path

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
            self.resources.append(
                SkillResource(
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
            self.scripts.append(
                SkillScript(
                    name=script_name,
                    description=script_description,
                    function=f,
                )
            )
            return f

        if func is None:
            return decorator
        return decorator(func)


# endregion

# region Script Runners


@runtime_checkable
class SkillScriptRunner(Protocol):
    """Protocol for skill script runners.

    .. warning:: Experimental

        This API is experimental and subject to change or removal
        in future versions without notice.

    A script runner determines how **file-based** skill scripts are
    run. Implementations decide the execution strategy
    (e.g., local subprocess, hosted code execution environment,
    user-provided callable).

    Code-defined scripts (registered via the ``@skill.script`` decorator)
    are always executed **in-process** and do not use a script runner.

    Any callable (sync or async) matching the ``__call__`` signature
    satisfies this protocol.
    """

    def __call__(self, skill: Skill, script: SkillScript, args: dict[str, Any] | None = None) -> Any:
        """Run a skill script.

        The :class:`SkillsProvider` resolves skill and script names
        before calling this method, so implementations receive fully
        resolved objects.

        Args:
            skill: The skill that owns the script.
            script: The script to run.
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
# must not start or end with a hyphen.
VALID_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$")

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
- Use `read_skill_resource` to read any referenced resources, using the name exactly as listed
   (e.g. `"style-guide"` not `"style-guide.md"`, `"references/FAQ.md"` not `"FAQ.md"`).
{runner_instructions}
Only load what is needed, when it is needed."""

SCRIPT_RUNNER_INSTRUCTIONS: Final[str] = (
    "\n- Use `run_skill_script` to run referenced scripts, using the name exactly as listed."
    "\n- Pass script arguments inside `args` as a JSON object"
    ' (e.g. `args: {"length": 24}`), not as top-level tool parameters.\n'
)

# endregion

# region SkillsProvider


class SkillsProvider(BaseContextProvider):
    """Context provider that advertises skills and exposes skill tools.

    .. warning:: Experimental

        This API is experimental and subject to change or removal
        in future versions without notice.

    Supports both **file-based** skills (discovered from ``SKILL.md`` files)
    and **code-defined** skills (passed as :class:`Skill` instances).

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
        File-based only:

        .. code-block:: python

            provider = SkillsProvider(skill_paths="./skills")

        Code-defined only:

        .. code-block:: python

            my_skill = Skill(
                name="my-skill",
                description="Example skill",
                content="Use this skill for ...",
            )
            provider = SkillsProvider(skills=[my_skill])

        Combined:

        .. code-block:: python

            provider = SkillsProvider(
                skill_paths="./skills",
                skills=[my_skill],
            )

    Attributes:
        DEFAULT_SOURCE_ID: Default value for the ``source_id`` used by this provider.
    """

    DEFAULT_SOURCE_ID: ClassVar[str] = "agent_skills"

    def __init__(
        self,
        skill_paths: str | Path | Sequence[str | Path] | None = None,
        *,
        skills: Sequence[Skill] | None = None,
        script_runner: SkillScriptRunner | None = None,
        instruction_template: str | None = None,
        resource_extensions: tuple[str, ...] | None = None,
        script_extensions: tuple[str, ...] | None = None,
        require_script_approval: bool = False,
        source_id: str | None = None,
    ) -> None:
        """Initialize a SkillsProvider.

        Args:
            skill_paths: One or more directory paths to search for file-based
                skills.  Each path may point to an individual skill folder
                (containing ``SKILL.md``) or to a parent that contains skill
                subdirectories.

        Keyword Args:
            skills: Code-defined :class:`Skill` instances to register.
            script_runner: Strategy for running **file-based** skill
                scripts. The provider resolves skill and script names, then
                calls the runner directly. This parameter only
                affects scripts discovered from disk (via *skill_paths*);
                code-defined scripts (registered with ``@skill.script``) are
                always executed in-process and ignore this setting.
                When ``None``, file-based scripts are not executable.
            instruction_template: Custom system-prompt template for
                advertising skills.  Must contain a ``{skills}`` placeholder for the
                generated skills list.  Uses a built-in template when ``None``.
            resource_extensions: File extensions recognized as discoverable
                resources.  Defaults to ``DEFAULT_RESOURCE_EXTENSIONS``
                (``(".md", ".json", ".yaml", ".yml", ".csv", ".xml", ".txt")``).
            script_extensions: File extensions recognized as discoverable
                scripts.  Defaults to ``DEFAULT_SCRIPT_EXTENSIONS``
                (``(".py",)``).
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
            source_id: Unique identifier for this provider instance.
        """
        super().__init__(source_id or self.DEFAULT_SOURCE_ID)

        self._skills = _load_skills(
            skill_paths,
            skills,
            resource_extensions or DEFAULT_RESOURCE_EXTENSIONS,
            script_extensions or DEFAULT_SCRIPT_EXTENSIONS,
        )

        # File-based skills (skill.path set) have scripts discovered from disk
        has_file_scripts = any(s.scripts for s in self._skills.values() if s.path is not None)

        # Code-defined skills (skill.path is None) have scripts with callable functions
        has_code_scripts = any(s.scripts for s in self._skills.values() if s.path is None)

        if has_file_scripts and script_runner is None:
            raise ValueError(
                "File-based skills with scripts were provided but no 'script_runner' was provided. "
                "Pass a SkillScriptRunner callable to SkillsProvider."
            )

        self._script_runner = script_runner

        self._instructions = _create_instructions(
            prompt_template=instruction_template,
            skills=self._skills,
            include_script_runner_instructions=has_file_scripts or has_code_scripts,
        )

        self._tools = self._create_tools(
            include_script_runner_tool=has_file_scripts or has_code_scripts,
            require_script_approval=require_script_approval,
        )

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject skill instructions and tools into the session context.

        Called by the framework before the agent runs.  When at least one
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
        if not self._skills:
            return

        context.extend_instructions(self.source_id, self._instructions)  # type: ignore[arg-type]
        context.extend_tools(self.source_id, self._tools)

    def _create_tools(
        self,
        include_script_runner_tool: bool,
        require_script_approval: bool = False,
    ) -> list[FunctionTool]:
        """Create the ``load_skill`` and ``read_skill_resource`` tool definitions.

        When *include_script_runner_tool* is ``True``, also creates
        ``run_skill_script``.

        Args:
            include_script_runner_tool: Whether to include the
                ``run_skill_script`` tool in the returned list.
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
                description="Reads a resource associated with a skill, such as references, assets, or dynamic data.",
                func=self._read_skill_resource,
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
        ]

        if include_script_runner_tool:
            tools.append(
                FunctionTool(
                    name="run_skill_script",
                    description="Runs a script associated with a skill.",
                    func=self._run_skill_script,
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

    def _load_skill(self, skill_name: str) -> str:
        """Return the full instructions for the named skill.

        For file-based skills the raw ``SKILL.md`` content is returned as-is.
        For code-defined skills the content is wrapped in XML metadata and,
        when resources exist, an ``<resources>`` element is appended.

        Args:
            skill_name: The name of the skill to load.

        Returns:
            The skill instructions text, or a user-facing error message if
            *skill_name* is empty or not found.
        """
        if not skill_name or not skill_name.strip():
            return "Error: Skill name cannot be empty."

        skill = self._skills.get(skill_name)
        if skill is None:
            return f"Error: Skill '{skill_name}' not found."

        logger.info("Loading skill: %s", skill_name)

        # File-based skills return raw content directly
        if skill.path:
            return skill.content

        # Code-defined skills: wrap in XML metadata
        content = (
            f"<name>{xml_escape(skill.name)}</name>\n"
            f"<description>{xml_escape(skill.description)}</description>\n"
            "\n"
            "<instructions>\n"
            f"{skill.content}\n"
            "</instructions>"
        )

        if skill.resources:
            resource_lines = "\n".join(_create_resource_element(r) for r in skill.resources)
            content += f"\n\n<resources>\n{resource_lines}\n</resources>"

        if skill.scripts:
            script_lines = "\n".join(_create_script_element(s) for s in skill.scripts)
            content += f"\n\n<scripts>\n{script_lines}\n</scripts>"

        return content

    async def _run_skill_script(
        self, skill_name: str, script_name: str, args: dict[str, Any] | None = None, **kwargs: Any
    ) -> Any:
        """Run a named script from a skill.

        For code-defined scripts (those with a ``function`` and no ``path``),
        the function is invoked directly in-process.  For file-based scripts
        the configured :class:`SkillScriptRunner` is used.

        Args:
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

        skill = self._skills.get(skill_name)
        if not skill:
            return f"Error: Skill '{skill_name}' not found."

        script = next((s for s in skill.scripts if s.name.lower() == script_name.lower()), None)
        if not script:
            return f"Error: Script '{script_name}' not found in skill '{skill_name}'."

        # Code-defined scripts: run the function directly
        if script.function is not None:
            try:
                if script._accepts_kwargs:  # pyright: ignore[reportPrivateUsage]
                    result = script.function(**(args or {}), **kwargs)
                else:
                    result = script.function(**(args or {}))
                if inspect.isawaitable(result):
                    result = await result
                return result
            except Exception:
                logger.exception("Error running code-defined script '%s' in skill '%s'", script_name, skill_name)
                return f"Error: Failed to run script '{script_name}' in skill '{skill_name}'."

        # File-based scripts: delegate to the runner
        if self._script_runner is None:
            return (
                f"Error: Script '{script_name}' in skill '{skill_name}' requires a runner. "
                "Provide a script_runner for file-based scripts."
            )
        try:
            result = self._script_runner(skill, script, args)
            if inspect.isawaitable(result):
                result = await result
            return result
        except Exception:
            logger.exception("Error running file-based script '%s' in skill '%s'", script_name, skill_name)
            return f"Error: Failed to run script '{script_name}' in skill '{skill_name}'."

    async def _read_skill_resource(self, skill_name: str, resource_name: str, **kwargs: Any) -> Any:
        """Read a named resource from a skill.

        Resolves the resource by case-insensitive name lookup.  Static
        ``content`` is returned directly; callable resources are invoked
        (awaited if async).

        Args:
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

        skill = self._skills.get(skill_name)
        if skill is None:
            return f"Error: Skill '{skill_name}' not found."

        # Find resource by name (case-insensitive)
        resource_name_lower = resource_name.lower()
        for resource in skill.resources:
            if resource.name.lower() == resource_name_lower:
                break
        else:
            return f"Error: Resource '{resource_name}' not found in skill '{skill_name}'."

        if resource.content is not None:
            return resource.content

        if resource.function is not None:
            try:
                if inspect.iscoroutinefunction(resource.function):
                    result = (
                        await resource.function(**kwargs) if resource._accepts_kwargs else await resource.function()  # pyright: ignore[reportPrivateUsage]
                    )
                else:
                    result = resource.function(**kwargs) if resource._accepts_kwargs else resource.function()  # pyright: ignore[reportPrivateUsage]
                return result
            except Exception:
                logger.exception("Failed to read resource '%s' from skill '%s'", resource_name, skill_name)
                return f"Error: Failed to read resource '{resource_name}' from skill '{skill_name}'."

        return f"Error: Resource '{resource.name}' has no content or function."


# endregion

# region Module-level helper functions


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


def _has_symlink_in_path(path: str, directory: str) -> bool:
    """Detect symlinks in the portion of *path* below *directory*.

    Only segments below *directory* are inspected; the directory itself
    and anything above it are not checked.

    **Precondition:** *path* must be a descendant of *directory*.
    Call :func:`_is_path_within_directory` first to verify containment.

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

        if not _is_path_within_directory(resource_full_path, root_directory_path):
            logger.warning(
                "Skipping resource '%s': resolves outside skill directory '%s'",
                resource_file,
                skill_dir_path,
            )
            continue

        if _has_symlink_in_path(resource_full_path, root_directory_path):
            logger.warning(
                "Skipping resource '%s': symlink detected in path under skill directory '%s'",
                resource_file,
                skill_dir_path,
            )
            continue

        rel_path = resource_file.relative_to(skill_dir)
        resources.append(_normalize_resource_path(str(rel_path)))

    return resources


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

        if not _is_path_within_directory(script_full_path, root_directory_path):
            logger.warning(
                "Skipping script '%s': resolves outside skill directory '%s'",
                script_file,
                skill_dir_path,
            )
            continue

        if _has_symlink_in_path(script_full_path, root_directory_path):
            logger.warning(
                "Skipping script '%s': symlink detected in path under skill directory '%s'",
                script_file,
                skill_dir_path,
            )
            continue

        rel_path = script_file.relative_to(skill_dir)
        scripts.append(_normalize_resource_path(str(rel_path)))

    return scripts


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
            "using only lowercase letters, numbers, and hyphens, and must not start or end with a hyphen."
        )

    if not description or not description.strip():
        return f"Skill '{name}' from '{source}' is missing a description."

    if len(description) > MAX_DESCRIPTION_LENGTH:
        return (
            f"Skill '{name}' from '{source}' has an invalid description: "
            f"Must be {MAX_DESCRIPTION_LENGTH} characters or fewer."
        )

    return None


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

    error = _validate_skill_metadata(name, description, skill_file_path)
    if error:
        logger.error(error)
        return None

    # name and description are guaranteed non-None after validation
    return name, description  # type: ignore[return-value]


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

    result = _extract_frontmatter(content, str(skill_file))
    if result is None:
        return None

    name, description = result
    return name, description, content


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


def _read_file_skill_resource(skill: Skill, resource_name: str) -> str:
    """Read a file-based resource from disk with security guards.

    Validates that the resolved path stays within the skill directory and
    does not traverse any symlinks before reading.

    Args:
        skill: The owning skill (must have a non-``None`` :attr:`~Skill.path`).
        resource_name: Relative path of the resource within the skill directory.

    Returns:
        The UTF-8 text content of the resource file.

    Raises:
        ValueError: If the resolved path escapes the skill directory,
            the file does not exist, or a symlink is detected in the path.
    """
    resource_name = _normalize_resource_path(resource_name)

    if not skill.path:
        raise ValueError(f"Skill '{skill.name}' has no path set; cannot read file-based resources.")

    resource_full_path = os.path.normpath(Path(skill.path) / resource_name)
    root_directory_path = os.path.normpath(skill.path)

    if not _is_path_within_directory(resource_full_path, root_directory_path):
        raise ValueError(f"Resource file '{resource_name}' references a path outside the skill directory.")

    if not Path(resource_full_path).is_file():
        raise ValueError(f"Resource file '{resource_name}' not found in skill '{skill.name}'.")

    if _has_symlink_in_path(resource_full_path, root_directory_path):
        raise ValueError(
            f"Resource file '{resource_name}' in skill '{skill.name}' "
            "has a symlink in its path; symlinks are not allowed."
        )

    logger.info("Reading resource '%s' from skill '%s'", resource_name, skill.name)
    return Path(resource_full_path).read_text(encoding="utf-8")


def _discover_file_skills(
    skill_paths: str | Path | Sequence[str | Path] | None,
    resource_extensions: tuple[str, ...] = DEFAULT_RESOURCE_EXTENSIONS,
    script_extensions: tuple[str, ...] = DEFAULT_SCRIPT_EXTENSIONS,
) -> dict[str, Skill]:
    """Discover, parse, and load all file-based skills from the given paths.

    Each discovered ``SKILL.md`` is parsed for metadata, and resource files
    in the same directory are wrapped in lazy-read closures that perform
    security checks (path traversal, symlink escape) at read time.

    Args:
        skill_paths: Directory path(s) to scan, or ``None`` to skip.
        resource_extensions: File extensions recognized as resources.
        script_extensions: File extensions recognized as scripts.

    Returns:
        A dict mapping skill name → :class:`Skill`.
    """
    if skill_paths is None:
        return {}

    resolved_paths: list[str] = (
        [str(skill_paths)] if isinstance(skill_paths, (str, Path)) else [str(p) for p in skill_paths]
    )

    skills: dict[str, Skill] = {}

    discovered = _discover_skill_directories(resolved_paths)
    logger.info("Discovered %d potential skills", len(discovered))

    for skill_path in discovered:
        parsed = _read_and_parse_skill_file(skill_path)
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

        file_skill = Skill(
            name=name,
            description=description,
            content=content,
            path=skill_path,
        )

        # Discover and attach file-based resources as SkillResource closures
        for rn in _discover_resource_files(skill_path, resource_extensions):
            reader = (lambda s, r: lambda: _read_file_skill_resource(s, r))(file_skill, rn)
            file_skill.resources.append(SkillResource(name=rn, function=reader))

        # Discover and attach file-based scripts as SkillScript instances
        for sn in _discover_script_files(skill_path, script_extensions):
            file_skill.scripts.append(SkillScript(name=sn, path=sn))

        skills[file_skill.name] = file_skill
        logger.info("Loaded skill: %s", file_skill.name)

    logger.info("Successfully loaded %d skills", len(skills))
    return skills


def _load_skills(
    skill_paths: str | Path | Sequence[str | Path] | None,
    skills: Sequence[Skill] | None,
    resource_extensions: tuple[str, ...],
    script_extensions: tuple[str, ...],
) -> dict[str, Skill]:
    """Discover and merge skills from file paths and code-defined skills.

    File-based skills are discovered first.  Code-defined skills are then
    merged in; if a code-defined skill has the same name as an existing
    file-based skill, the code-defined one is skipped with a warning.

    Args:
        skill_paths: Directory path(s) to scan for ``SKILL.md`` files, or ``None``.
        skills: Code-defined :class:`Skill` instances, or ``None``.
        resource_extensions: File extensions recognized as discoverable resources.
        script_extensions: File extensions recognized as discoverable scripts.

    Returns:
        A dict mapping skill name → :class:`Skill`.
    """
    result = _discover_file_skills(skill_paths, resource_extensions, script_extensions)

    if skills:
        for code_skill in skills:
            error = _validate_skill_metadata(code_skill.name, code_skill.description, "code skill")
            if error:
                logger.warning(error)
                continue
            if code_skill.name in result:
                logger.warning(
                    "Duplicate skill name '%s': code skill skipped in favor of existing skill",
                    code_skill.name,
                )
                continue
            result[code_skill.name] = code_skill
            logger.info("Registered code skill: %s", code_skill.name)

    return result


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


def _create_instructions(
    prompt_template: str | None,
    skills: dict[str, Skill],
    include_script_runner_instructions: bool = False,
) -> str | None:
    """Create the system-prompt text that advertises available skills.

    Generates an XML list of ``<skill>`` elements (sorted by name) and
    inserts it into *prompt_template* at the ``{skills}`` placeholder.
    When *include_script_runner_instructions* is ``True``, executor-provided
    instructions are inserted at the ``{runner_instructions}`` placeholder.

    Args:
        prompt_template: Custom template string with ``{skills}`` and
            optional ``{runner_instructions}`` placeholders,
            or ``None`` to use the built-in default.
        skills: Registered skills keyed by name.
        include_script_runner_instructions: When ``True``, include
            script-runner instructions in the generated prompt.
            Defaults to ``False``.

    Returns:
        The formatted instruction string, or ``None`` when *skills* is empty.

    Raises:
        ValueError: If *prompt_template* is not a valid format string
            (e.g. missing ``{skills}`` placeholder).
    """
    runner_instructions = SCRIPT_RUNNER_INSTRUCTIONS if include_script_runner_instructions else None
    template = DEFAULT_SKILLS_INSTRUCTION_PROMPT

    if prompt_template is not None:
        # Validate that the custom template contains a valid {skills} placeholder
        try:
            result = prompt_template.format(skills="__PROBE__", runner_instructions="__EXEC_PROBE__")
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
        template = prompt_template

    if not skills:
        return None

    lines: list[str] = []
    # Sort by name for deterministic output
    for skill in sorted(skills.values(), key=lambda s: s.name):
        lines.append("  <skill>")
        lines.append(f"    <name>{xml_escape(skill.name)}</name>")
        lines.append(f"    <description>{xml_escape(skill.description)}</description>")
        lines.append("  </skill>")

    return template.format(
        skills="\n".join(lines),
        runner_instructions=runner_instructions or "",
    )


# endregion
