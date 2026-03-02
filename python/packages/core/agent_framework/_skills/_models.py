# Copyright (c) Microsoft. All rights reserved.

"""Skill data models.

Defines :class:`SkillResource` and :class:`Skill`, the core
data model classes for the agent skills system.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


class SkillResource:
    """A named piece of supplementary content attached to a skill.

    .. warning:: Experimental

        This API is experimental and subject to change or removal
        in future versions without notice.

    A resource provides data that an agent can retrieve on demand.  It holds
    either a static ``content`` string or a ``function`` that produces content
    dynamically (sync or async).  Exactly one must be provided.

    Args:
        name: Identifier for this resource (e.g. ``"reference"``, ``"get-schema"``).
        description: Optional human-readable summary shown when advertising the resource.
        content: Static content string.  Mutually exclusive with *function*.
        function: Callable (sync or async) that returns content on demand.
            Mutually exclusive with *content*.

    Attributes:
        name: Resource identifier.
        description: Optional human-readable summary, or ``None``.
        content: Static content string, or ``None`` if backed by a callable.
        function: Callable that returns content, or ``None`` if backed by static content.

    Examples:
        Static resource::

            SkillResource(name="reference", content="Static docs here...")

        Callable resource::

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


class Skill:
    """A skill definition with optional resources.

    .. warning:: Experimental

        This API is experimental and subject to change or removal
        in future versions without notice.

    A skill bundles a set of instructions (``content``) with metadata and
    zero or more :class:`SkillResource` instances.  Resources can be
    supplied at construction time or added later via the :meth:`resource`
    decorator.

    Args:
        name: Skill name (lowercase letters, numbers, hyphens only).
        description: Human-readable description of the skill (≤1024 chars).
        content: The skill instructions body.
        resources: Pre-built resources to attach to this skill.
        path: Absolute path to the skill directory on disk.  Set automatically
            for file-based skills; leave as ``None`` for code-defined skills.

    Attributes:
        name: Skill name (lowercase letters, numbers, hyphens only).
        description: Human-readable description of the skill.
        content: The skill instructions body.
        resources: Mutable list of :class:`SkillResource` instances.
        path: Absolute path to the skill directory on disk, or ``None``
            for code-defined skills.

    Examples:
        Direct construction::

            skill = Skill(
                name="my-skill",
                description="A skill example",
                content="Use this skill for ...",
                resources=[SkillResource(name="ref", content="...")],
            )

        With dynamic resources::

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
        path: str | None = None,
    ) -> None:
        if not name or not name.strip():
            raise ValueError("Skill name cannot be empty.")
        if not description or not description.strip():
            raise ValueError("Skill description cannot be empty.")

        self.name = name
        self.description = description
        self.content = content
        self.resources: list[SkillResource] = resources if resources is not None else []
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
            Bare decorator::

                @skill.resource
                def get_schema() -> str:
                    return "schema..."

            With arguments::

                @skill.resource(name="custom-name", description="Custom desc")
                async def get_data() -> str:
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
