# Copyright (c) Microsoft. All rights reserved.

"""Built-in orchestration types must survive a checkpoint round trip.

Checkpoint restore runs pickle through a restricted unpickler. Its default allowlist
auto-trusts the dotted ``agent_framework.`` prefix, which covers core but not sibling
distributions like ``agent_framework_orchestrations``, so framework-owned orchestration
envelopes have to opt in by name. Importing the package is what registers them (#7789).

These tests use a ``FileCheckpointStorage`` built with **no** ``allowed_checkpoint_types``,
because the bug was precisely that users had to supply framework-internal module paths
themselves. Each payload is fully populated: the unpickler resolves nested classes as well
as the outer one, so a test that only round-trips an empty shell would still pass with a
nested type left unregistered.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
from agent_framework import AgentResponse, Executor, Message, WorkflowCheckpoint, WorkflowContext, handler
from agent_framework._workflows._checkpoint import FileCheckpointStorage

from agent_framework_orchestrations import (
    AgentRequestInfoResponse,
    GroupChatBuilder,
    HandoffAgentUserRequest,
    MagenticPlanReviewRequest,
    MagenticPlanReviewResponse,
    MagenticProgressLedger,
    MagenticProgressLedgerItem,
    MagenticResetSignal,
)
from agent_framework_orchestrations._base_group_chat_orchestrator import (
    GroupChatParticipantMessage,
    GroupChatRequestMessage,
    GroupChatResponseMessage,
)


def _ledger() -> MagenticProgressLedger:
    """A fully populated progress ledger; every field is a nested dataclass."""
    return MagenticProgressLedger(
        is_request_satisfied=MagenticProgressLedgerItem(reason="not yet", answer=False),
        is_in_loop=MagenticProgressLedgerItem(reason="no repeats", answer=False),
        is_progress_being_made=MagenticProgressLedgerItem(reason="advancing", answer=True),
        next_speaker=MagenticProgressLedgerItem(reason="their turn", answer="researcher"),
        instruction_or_question=MagenticProgressLedgerItem(reason="needs detail", answer="Find the source."),
    )


def _payloads() -> list[tuple[str, Any]]:
    """One populated instance of every orchestration type that crosses a checkpoint."""
    msg = Message(role="assistant", contents=["hello"])
    return [
        ("GroupChatRequestMessage", GroupChatRequestMessage(additional_instruction="go", metadata={"round": 1})),
        ("GroupChatParticipantMessage", GroupChatParticipantMessage(messages=[msg])),
        ("GroupChatResponseMessage", GroupChatResponseMessage(message=msg)),
        ("MagenticResetSignal", MagenticResetSignal()),
        ("HandoffAgentUserRequest", HandoffAgentUserRequest(agent_response=AgentResponse(messages=[msg]))),
        ("AgentRequestInfoResponse", AgentRequestInfoResponse(messages=[msg])),
        ("MagenticPlanReviewResponse", MagenticPlanReviewResponse(review=[msg])),
        (
            # The nested case: `current_progress` is non-None, so restoring this request
            # forces the unpickler to resolve MagenticProgressLedger and
            # MagenticProgressLedgerItem as well. Registering only the outer request would
            # leave this failing.
            "MagenticPlanReviewRequest",
            MagenticPlanReviewRequest(plan=msg, current_progress=_ledger(), is_stalled=True),
        ),
    ]


@pytest.mark.parametrize("name,payload", _payloads(), ids=[n for n, _ in _payloads()])
async def test_orchestration_type_survives_checkpoint_round_trip(name: str, payload: Any) -> None:
    """Saving and restoring a built-in orchestration payload needs no user allowlist."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)  # deliberately no allowed_checkpoint_types
        await storage.save(
            WorkflowCheckpoint(
                workflow_name="orchestration",
                graph_signature_hash="test-hash",
                checkpoint_id=f"ck-{name}",
                state={"payload": payload},
            )
        )
        restored = await storage.load(f"ck-{name}")

    assert type(restored.state["payload"]) is type(payload)


async def test_plan_review_request_restores_its_nested_progress_ledger() -> None:
    """The nested ledger must come back with its values, not merely resolve as a class.

    Separate from the round-trip case above because the failure it guards is different: a
    missing registration for `MagenticProgressLedgerItem` raises during unpickling, while a
    ledger that resolves but loses its contents would pass a type-only assertion.
    """
    request = MagenticPlanReviewRequest(
        plan=Message(role="assistant", contents=["the plan"]),
        current_progress=_ledger(),
        is_stalled=True,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)
        await storage.save(
            WorkflowCheckpoint(
                workflow_name="magentic",
                graph_signature_hash="test-hash",
                checkpoint_id="ck-nested",
                state={"payload": request},
            )
        )
        restored = await storage.load("ck-nested")

    payload = restored.state["payload"]
    assert isinstance(payload, MagenticPlanReviewRequest)
    assert payload.is_stalled is True

    progress = payload.current_progress
    assert isinstance(progress, MagenticProgressLedger)
    assert isinstance(progress.next_speaker, MagenticProgressLedgerItem)
    assert progress.next_speaker.answer == "researcher"
    assert progress.is_request_satisfied.answer is False
    assert progress.instruction_or_question.reason == "needs detail"


def test_registration_happens_on_package_import() -> None:
    """Importing the package is what makes restore work, so pin that it registers.

    A checkpoint written by a process that imported the orchestrations package can only be
    restored by one that also imports it. That import-order dependency is the cost of
    opting in by name rather than widening the trusted module prefix, and it is worth
    stating in a test rather than leaving implicit.
    """
    from agent_framework._workflows._checkpoint_encoding import _REGISTERED_CHECKPOINT_TYPE_KEYS

    prefix = "agent_framework_orchestrations."
    registered = {key for key in _REGISTERED_CHECKPOINT_TYPE_KEYS if key.startswith(prefix)}

    expected = {
        "agent_framework_orchestrations._base_group_chat_orchestrator:GroupChatRequestMessage",
        "agent_framework_orchestrations._base_group_chat_orchestrator:GroupChatParticipantMessage",
        "agent_framework_orchestrations._base_group_chat_orchestrator:GroupChatResponseMessage",
        "agent_framework_orchestrations._handoff:HandoffAgentUserRequest",
        "agent_framework_orchestrations._orchestration_request_info:AgentRequestInfoResponse",
        "agent_framework_orchestrations._magentic:MagenticResetSignal",
        "agent_framework_orchestrations._magentic:MagenticPlanReviewRequest",
        "agent_framework_orchestrations._magentic:MagenticPlanReviewResponse",
        "agent_framework_orchestrations._magentic:MagenticProgressLedger",
        "agent_framework_orchestrations._magentic:MagenticProgressLedgerItem",
    }
    assert expected <= registered


class _CustomParticipant(Executor):
    """A non-agent group-chat participant.

    Defined at module scope on purpose: with ``from __future__ import annotations`` a
    handler declared inside a function body cannot resolve its own context annotation.
    """

    @handler
    async def on_request(
        self, message: GroupChatRequestMessage, ctx: WorkflowContext[GroupChatResponseMessage]
    ) -> None:
        await ctx.send_message(GroupChatResponseMessage(message=Message(role="assistant", contents=["custom reply"])))

    @handler
    async def on_broadcast(self, message: GroupChatParticipantMessage, ctx: WorkflowContext) -> None:
        pass


async def test_group_chat_with_a_custom_executor_participant_keeps_every_checkpoint_readable() -> None:
    """End-to-end: the scenario that actually produces the envelopes, restored from disk.

    The orchestrator only wraps traffic in the group-chat envelopes for participants that
    are **not** agents (``_base_group_chat_orchestrator.py:434,467``); agent participants
    get a core ``AgentExecutorRequest``, which the default allowlist already trusts. So a
    group chat built purely from agents never hit this bug, and neither did the existing
    suite -- which is why it shipped.

    The symptom is worse than a failed ``load()``. ``list_checkpoints`` logs and skips a
    checkpoint it cannot decode, so unregistered types make checkpoints silently vanish
    from listings and ``get_latest`` hands back a stale one instead of raising. This test
    therefore counts the files on disk rather than trusting the listing.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileCheckpointStorage(temp_dir)  # deliberately no allowed_checkpoint_types
        workflow = GroupChatBuilder(
            participants=[_CustomParticipant(id="custom")],
            max_rounds=2,
            checkpoint_storage=storage,
            selection_func=lambda state: "custom",
        ).build()

        async for _ in workflow.run("test task", stream=True):
            pass

        on_disk = await asyncio.to_thread(lambda: sorted(p.stem for p in Path(temp_dir).glob("*.json")))
        assert on_disk, "the run produced no checkpoints, so this test proves nothing"

        # Every checkpoint on disk must load individually...
        for checkpoint_id in on_disk:
            await storage.load(checkpoint_id)

        # ...and the listing must agree with the disk, rather than quietly dropping the
        # ones it could not decode.
        listed = await storage.list_checkpoints(workflow_name=workflow.name)
        assert sorted(cp.checkpoint_id for cp in listed) == on_disk
