# Copyright (c) Microsoft. All rights reserved.

"""Native A2A card adapters for Agent Framework targets."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar, cast

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Part
from a2a.types import Message as A2AMessage
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    Message,
    Skill,
    SkillsProvider,
    SkillsSourceContext,
    SupportsAgentRun,
    Workflow,
    WorkflowRunResult,
)
from agent_framework_hosting import AgentRunArgs, AgentState, WorkflowState

from ._conversion import (
    _normalized_modes,  # pyright: ignore[reportPrivateUsage]
    _workflow_input_type,  # pyright: ignore[reportPrivateUsage]
    _workflow_type_modes,  # pyright: ignore[reportPrivateUsage]
)
from ._conversion import (
    a2a_from_run as _a2a_from_run,
)
from ._conversion import (
    a2a_from_workflow_run as _a2a_from_workflow_run,
)
from ._conversion import (
    a2a_to_run as _a2a_to_run,
)
from ._conversion import (
    a2a_to_workflow_run as _a2a_to_workflow_run,
)

AgentT = TypeVar("AgentT", bound=SupportsAgentRun)
WorkflowT = TypeVar("WorkflowT", bound=Workflow)


def _to_a2a_skill(skill: AgentSkill | Skill, input_modes: Sequence[str], output_modes: Sequence[str]) -> AgentSkill:
    if isinstance(skill, AgentSkill):
        return skill

    frontmatter = skill.frontmatter
    return AgentSkill(
        id=frontmatter.name,
        name=frontmatter.name,
        description=frontmatter.description,
        tags=[frontmatter.name],
        examples=[],
        input_modes=input_modes,
        output_modes=output_modes,
    )


class AgentA2AAdapter(Generic[AgentT]):
    """Resolve a native A2A card from Agent Framework agent metadata."""

    def __init__(
        self,
        target: AgentT | AgentState[AgentT],
        *,
        version: str,
        supported_interfaces: Sequence[AgentInterface],
        skills: Sequence[AgentSkill | Skill] = (),
        infer_skills: bool = True,
        capabilities: AgentCapabilities | None = None,
        name: str | None = None,
        description: str | None = None,
        default_input_modes: Sequence[str] = ("text",),
        default_output_modes: Sequence[str] = ("text",),
    ) -> None:
        """Create an agent-backed A2A card adapter.

        Args:
            target: Agent or existing ``AgentState`` whose public metadata
                should seed the card.

        Keyword Args:
            version: Application-defined version advertised by the A2A server.
            supported_interfaces: Public A2A endpoints exposed by the application,
                with one native interface for each available protocol binding. For
                example, ``from a2a.types import AgentInterface`` and then
                ``[AgentInterface(url="https://example.com/a2a",
                protocol_binding="JSONRPC")]``.
            skills: Explicit native A2A or Agent Framework skills.
            infer_skills: Whether to discover Agent Framework skills from
                ``SkillsProvider`` instances on the resolved agent. Defaults to ``True``.
            capabilities: Native server capabilities. Defaults to no optional capabilities.
            name: Public card name override. Defaults to the resolved target name.
            description: Public card description override. Defaults to the resolved target description.
            default_input_modes: Input modes advertised by the card. Defaults to
                ``("text",)``. Other A2A mode strings may include
                ``"application/json"``, ``"application/octet-stream"``, or media
                types such as ``"image/png"``; these examples are not exhaustive.
            default_output_modes: Output modes advertised by the card. Defaults
                to ``("text",)`` and accepts the same A2A mode strings as
                ``default_input_modes``.

        Raises:
            ValueError: If required application-owned card values are missing.
        """
        if not version:
            raise ValueError("An A2A agent card requires a version.")
        if not supported_interfaces:
            raise ValueError("An A2A agent card requires at least one supported interface.")
        if not default_input_modes or not default_output_modes:
            raise ValueError("An A2A agent card requires at least one input and output mode.")
        _normalized_modes(default_input_modes)
        _normalized_modes(default_output_modes)

        self.state = target if isinstance(target, AgentState) else AgentState(target)
        self.version = version
        self.supported_interfaces = tuple(supported_interfaces)
        self.skills = tuple(skills)
        self.infer_skills = infer_skills
        self.capabilities = capabilities
        self.name = name
        self.description = description
        self.default_input_modes = tuple(default_input_modes)
        self.default_output_modes = tuple(default_output_modes)

    async def get_card(self) -> AgentCard:
        """Return the native A2A card for the resolved agent.

        Returns:
            A native A2A ``AgentCard``.

        Raises:
            ValueError: If the resolved target does not provide required public metadata.
        """
        target = await self.state.get_target()
        card_name = self.name if self.name is not None else target.name
        card_description = self.description if self.description is not None else target.description
        if not card_name:
            raise ValueError("An A2A agent card requires a name.")
        if not card_description:
            raise ValueError("An A2A agent card requires a description.")

        skills: list[AgentSkill | Skill] = list(self.skills)
        if self.infer_skills:
            providers = cast("Sequence[object]", getattr(target, "context_providers", ()))
            source_context = SkillsSourceContext(agent=target)
            for provider in providers:
                if isinstance(provider, SkillsProvider):
                    discovered = await provider._source.get_skills(  # pyright: ignore[reportPrivateUsage]
                        source_context
                    )
                    skills.extend(discovered)

        card_skills: list[AgentSkill] = []
        skill_ids: set[str] = set()
        for skill in skills:
            a2a_skill = _to_a2a_skill(skill, self.default_input_modes, self.default_output_modes)
            if a2a_skill.id not in skill_ids:
                skill_ids.add(a2a_skill.id)
                card_skills.append(a2a_skill)

        return AgentCard(
            name=card_name,
            description=card_description,
            version=self.version,
            default_input_modes=self.default_input_modes,
            default_output_modes=self.default_output_modes,
            capabilities=self.capabilities if self.capabilities is not None else AgentCapabilities(),
            supported_interfaces=self.supported_interfaces,
            skills=card_skills,
        )

    def a2a_to_run(
        self,
        message: A2AMessage,
        *,
        stream: bool = False,
        validate_modes: bool = True,
    ) -> AgentRunArgs:
        """Convert a native A2A message into Agent Framework run arguments.

        Args:
            message: Native A2A message to convert.

        Keyword Args:
            stream: Whether the caller intends to run the agent in streaming mode.
            validate_modes: Whether to validate parts against the card's
                ``default_input_modes``. Defaults to ``True``.

        Returns:
            Arguments corresponding to ``Agent.run(...)``.

        Raises:
            ValueError: If mode validation fails.
        """
        return _a2a_to_run(
            message,
            stream=stream,
            input_modes=self.default_input_modes if validate_modes else None,
        )

    def a2a_from_run(
        self,
        result: AgentResponse[Any] | Message | AgentResponseUpdate,
        *,
        validate_modes: bool = True,
    ) -> list[Part]:
        """Convert Agent Framework output into native A2A parts.

        Args:
            result: Completed response, response message, or streaming update.

        Keyword Args:
            validate_modes: Whether to validate parts against the card's
                ``default_output_modes``. Defaults to ``True``.

        Returns:
            Native A2A parts ready for an A2A SDK message or artifact.

        Raises:
            ValueError: If mode validation fails.
        """
        return _a2a_from_run(
            result,
            output_modes=self.default_output_modes if validate_modes else None,
        )


class WorkflowA2AAdapter(Generic[WorkflowT]):
    """Resolve a native A2A card from Agent Framework workflow metadata."""

    def __init__(
        self,
        target: WorkflowT | WorkflowState[WorkflowT],
        *,
        version: str,
        supported_interfaces: Sequence[AgentInterface],
        skills: Sequence[AgentSkill | Skill] = (),
        capabilities: AgentCapabilities | None = None,
        name: str | None = None,
        description: str | None = None,
        default_input_modes: Sequence[str] | None = None,
        default_output_modes: Sequence[str] | None = None,
    ) -> None:
        """Create a workflow-backed A2A card adapter.

        Args:
            target: Workflow or existing ``WorkflowState`` whose metadata and
                declared types should seed the card.

        Keyword Args:
            version: Application-defined version advertised by the A2A server.
            supported_interfaces: Public A2A endpoints exposed by the application,
                with one native interface for each available protocol binding. For
                example, ``from a2a.types import AgentInterface`` and then
                ``[AgentInterface(url="https://example.com/a2a",
                protocol_binding="JSONRPC")]``.
            skills: Explicit native A2A or Agent Framework skills.
            capabilities: Native server capabilities. Defaults to no optional capabilities.
            name: Public card name override. Defaults to the resolved workflow name.
            description: Public card description override. Defaults to the resolved workflow description.
            default_input_modes: Input mode override. ``None`` or an empty sequence
                infers modes from the start executor. Explicit alternatives include
                ``"text"``, ``"application/json"``, ``"application/octet-stream"``,
                and media types such as ``"image/png"``; A2A mode strings are
                extensible, so these examples are not exhaustive.
            default_output_modes: Output mode override. ``None`` or an empty sequence
                infers modes from declared workflow outputs and accepts the same
                explicit A2A mode strings as ``default_input_modes``.

        Raises:
            ValueError: If required application-owned card values are missing.
        """
        if not version:
            raise ValueError("An A2A workflow card requires a version.")
        if not supported_interfaces:
            raise ValueError("An A2A workflow card requires at least one supported interface.")
        if default_input_modes:
            _normalized_modes(default_input_modes)
        if default_output_modes:
            _normalized_modes(default_output_modes)
        self.state = target if isinstance(target, WorkflowState) else WorkflowState(target)
        self.version = version
        self.supported_interfaces = tuple(supported_interfaces)
        self.skills = tuple(skills)
        self.capabilities = capabilities
        self.name = name
        self.description = description
        self.default_input_modes = tuple(default_input_modes) if default_input_modes else None
        self.default_output_modes = tuple(default_output_modes) if default_output_modes else None
        self._resolved_output_modes: tuple[str, ...] | None = self.default_output_modes

    async def get_card(self) -> AgentCard:
        """Return the native A2A card for the resolved workflow.

        Returns:
            A native A2A ``AgentCard``.

        Raises:
            ValueError: If required metadata or modes cannot be determined.
        """
        target = await self.state.get_target()
        card_name = self.name if self.name is not None else target.name
        card_description = self.description if self.description is not None else target.description
        if not card_name:
            raise ValueError("An A2A workflow card requires a name.")
        if not card_description:
            raise ValueError("An A2A workflow card requires a description.")

        input_modes = (
            list(self.default_input_modes)
            if self.default_input_modes is not None
            else _workflow_type_modes(_workflow_input_type(target))
        )
        if self.default_output_modes is not None:
            output_modes = list(self.default_output_modes)
        elif target.output_types:
            inferred_modes = {mode for output_type in target.output_types for mode in _workflow_type_modes(output_type)}
            output_modes = [
                mode for mode in ("text", "application/octet-stream", "application/json") if mode in inferred_modes
            ]
        else:
            raise ValueError("Cannot infer A2A output modes because the workflow declares no output types.")
        self._resolved_output_modes = tuple(output_modes)

        return AgentCard(
            name=card_name,
            description=card_description,
            version=self.version,
            default_input_modes=input_modes,
            default_output_modes=output_modes,
            capabilities=self.capabilities if self.capabilities is not None else AgentCapabilities(),
            supported_interfaces=self.supported_interfaces,
            skills=[_to_a2a_skill(skill, input_modes, output_modes) for skill in self.skills],
        )

    async def a2a_to_run(self, message: A2AMessage, *, validate_modes: bool = True) -> Any:
        """Convert a native A2A message into validated workflow input.

        Args:
            message: Native A2A message containing the workflow input.

        Keyword Args:
            validate_modes: Whether to validate parts against the card's
                effective input modes. Defaults to ``True``.

        Returns:
            A value validated for ``Workflow.run(...)``.

        Raises:
            ValueError: If workflow input or mode validation fails.
        """
        target = await self.state.get_target()
        input_modes = (
            list(self.default_input_modes)
            if self.default_input_modes is not None
            else _workflow_type_modes(_workflow_input_type(target))
        )
        return _a2a_to_workflow_run(
            message,
            target,
            input_modes=input_modes if validate_modes else None,
        )

    def a2a_from_run(self, result: WorkflowRunResult, *, validate_modes: bool = True) -> list[Part]:
        """Convert completed workflow outputs into native A2A parts.

        Args:
            result: Completed non-streaming workflow result.

        Keyword Args:
            validate_modes: Whether to validate parts against the card's
                effective output modes. Defaults to ``True``. When output modes
                are inferred, call :meth:`get_card` before enabling validation.

        Returns:
            Native A2A parts for the workflow's public outputs.

        Raises:
            RuntimeError: If validation requires inferred output modes and
                :meth:`get_card` has not resolved them.
            ValueError: If workflow output or mode validation fails.
        """
        if validate_modes and self._resolved_output_modes is None:
            raise RuntimeError("Call `await adapter.get_card()` before validating inferred workflow output modes.")
        return _a2a_from_workflow_run(
            result,
            output_modes=self._resolved_output_modes if validate_modes else None,
        )
