# Copyright (c) Microsoft. All rights reserved.

"""Participant-oriented workflow output configuration helpers."""

from collections.abc import Sequence
from typing import Any, Literal

from agent_framework import SupportsAgentRun
from agent_framework._workflows._agent_utils import resolve_agent_id
from agent_framework._workflows._executor import Executor

_MISSING = object()
_ALL_OUTPUTS: Literal["all"] = "all"
_ALL_OTHER_OUTPUTS: Literal["all_other"] = "all_other"
_ParticipantOutputSpecifier = str | SupportsAgentRun | Executor
_ParticipantOutputSelection = Sequence[_ParticipantOutputSpecifier] | Literal["all"] | None
_ParticipantIntermediateOutputSelection = Sequence[_ParticipantOutputSpecifier] | Literal["all", "all_other"] | None
_WorkflowExecutorSpecifier = Executor | SupportsAgentRun


def _coalesce_output_from(  # pyright: ignore[reportUnusedFunction]
    *,
    output_from: Any = _MISSING,
) -> _ParticipantOutputSelection:
    """Resolve orchestration output selection to ``output_from``."""
    if output_from is not _MISSING:
        return _coerce_output_from(output_from)
    return None


def _coerce_output_from(output_from: Any) -> _ParticipantOutputSelection:
    """Coerce workflow-output participant selection while preserving the ``"all"`` literal."""
    if output_from is None:
        return None
    if isinstance(output_from, str):
        if output_from == _ALL_OUTPUTS:
            return _ALL_OUTPUTS
        if output_from == _ALL_OTHER_OUTPUTS:
            raise ValueError("output_from='all_other' is invalid; use intermediate_output_from='all_other' instead.")
        raise ValueError(f"Unsupported output_from literal {output_from!r}; use 'all' or a list of participants.")
    return list(output_from)


def _coerce_intermediate_output_from(  # pyright: ignore[reportUnusedFunction]
    intermediate_output_from: Any,
) -> _ParticipantIntermediateOutputSelection:
    """Coerce intermediate-output participant selection while preserving ``"all_other"``."""
    if intermediate_output_from is None:
        return None
    if isinstance(intermediate_output_from, str):
        if intermediate_output_from == _ALL_OUTPUTS:
            return _ALL_OUTPUTS
        if intermediate_output_from == _ALL_OTHER_OUTPUTS:
            return _ALL_OTHER_OUTPUTS
        raise ValueError(
            f"Unsupported intermediate_output_from literal {intermediate_output_from!r}; "
            "use 'all', 'all_other', or a list of participants."
        )
    return list(intermediate_output_from)


def _resolve_participant_output_config(  # pyright: ignore[reportUnusedFunction]
    *,
    participants: Sequence[Executor],
    output_from: _ParticipantOutputSelection,
    intermediate_output_from: _ParticipantIntermediateOutputSelection,
    default_output_from: Sequence[Executor] = (),
    extra_output_executors: Sequence[Executor] = (),
) -> tuple[list[_WorkflowExecutorSpecifier], list[_WorkflowExecutorSpecifier]]:
    """Resolve public participant output config into workflow executor config."""
    explicit_config = output_from is not None or intermediate_output_from is not None
    if explicit_config and not (output_from or intermediate_output_from):
        raise ValueError("output_from and intermediate_output_from cannot both be empty.")

    participants_by_id = {participant.id: participant for participant in participants}
    known_participants = sorted(participants_by_id)

    if output_from == _ALL_OUTPUTS:
        output_designated = list(participants)
    elif output_from is not None:
        output_designated = _resolve_designated_participants(
            output_from,
            kind="output",
            participants_by_id=participants_by_id,
            known_participants=known_participants,
        )
    elif intermediate_output_from in (_ALL_OTHER_OUTPUTS, _ALL_OUTPUTS):
        output_designated = []
    else:
        intermediate_designated = (
            _resolve_designated_participants(
                intermediate_output_from,
                kind="intermediate",
                participants_by_id=participants_by_id,
                known_participants=known_participants,
            )
            if intermediate_output_from is not None
            else []
        )
        # The caller-supplied default applies only to participants not explicitly designated as
        # intermediate. Without this subtraction, builders that pre-populate a default output list
        # (Handoff defaults to all participants, Sequential defaults to the last) would force
        # an overlap error whenever a user passed `intermediate_output_from=[X]` for an X in
        # the default set, contradicting the public docstring contract.
        intermediate_ids = {participant.id for participant in intermediate_designated}
        output_designated = [
            participant for participant in default_output_from if participant.id not in intermediate_ids
        ]

    if intermediate_output_from == _ALL_OUTPUTS:
        intermediate_designated = list(participants)
    elif intermediate_output_from == _ALL_OTHER_OUTPUTS:
        output_ids = {participant.id for participant in output_designated}
        intermediate_designated = [participant for participant in participants if participant.id not in output_ids]
    elif intermediate_output_from is not None:
        intermediate_designated = _resolve_designated_participants(
            intermediate_output_from,
            kind="intermediate",
            participants_by_id=participants_by_id,
            known_participants=known_participants,
        )
    else:
        intermediate_designated = []

    overlap = sorted(
        {participant.id for participant in output_designated}.intersection(
            participant.id for participant in intermediate_designated
        )
    )
    if overlap:
        raise ValueError(f"Participants cannot be both output and intermediate designated: {overlap}")

    output_executors: list[_WorkflowExecutorSpecifier] = [*extra_output_executors, *output_designated]
    intermediate_executors: list[_WorkflowExecutorSpecifier] = list(intermediate_designated)
    return output_executors, intermediate_executors


def _resolve_designated_participants(
    designations: Sequence[_ParticipantOutputSpecifier],
    *,
    kind: str,
    participants_by_id: dict[str, Executor],
    known_participants: Sequence[str],
) -> list[Executor]:
    resolved: list[Executor] = []
    seen: set[str] = set()
    for designation in designations:
        participant_id = _participant_id(designation)
        if participant_id in seen:
            raise ValueError(f"Duplicate {kind} participant '{participant_id}' in {kind}_participants.")
        seen.add(participant_id)
        try:
            resolved.append(participants_by_id[participant_id])
        except KeyError as exc:
            raise ValueError(
                f"Unknown {kind} participant '{participant_id}'. Known participants: {known_participants}"
            ) from exc
    return resolved


def _participant_id(participant: _ParticipantOutputSpecifier) -> str:
    if isinstance(participant, str):
        return participant
    if isinstance(participant, Executor):
        return participant.id
    return resolve_agent_id(participant)
