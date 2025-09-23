# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Any

import pytest

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    Executor,
    MagenticBuilder,
    MagenticManagerBase,
    MagenticPlanReviewDecision,
    MagenticPlanReviewReply,
    MagenticPlanReviewRequest,
    MagenticProgressLedger,
    MagenticProgressLedgerItem,
    RequestInfoEvent,
    Role,
    TextContent,
    WorkflowContext,
    WorkflowEvent,  # type: ignore  # noqa: E402
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    handler,
)
from agent_framework._agents import BaseAgent
from agent_framework._clients import ChatClientProtocol as AFChatClient
from agent_framework._workflow._magentic import (
    MagenticContext,
    MagenticStartMessage,
)


def test_magentic_start_message_from_string():
    msg = MagenticStartMessage.from_string("Do the thing")
    assert isinstance(msg, MagenticStartMessage)
    assert isinstance(msg.task, ChatMessage)
    assert msg.task.role == Role.USER
    assert msg.task.text == "Do the thing"


def test_plan_review_request_defaults_and_reply_variants():
    req = MagenticPlanReviewRequest()  # defaults provided by dataclass
    assert hasattr(req, "request_id")
    assert req.task_text == "" and req.facts_text == "" and req.plan_text == ""
    assert isinstance(req.round_index, int) and req.round_index == 0

    # Replies: approve, revise with comments, revise with edited text
    approve = MagenticPlanReviewReply(decision=MagenticPlanReviewDecision.APPROVE)
    revise_comments = MagenticPlanReviewReply(decision=MagenticPlanReviewDecision.REVISE, comments="Tighten scope")
    revise_text = MagenticPlanReviewReply(
        decision=MagenticPlanReviewDecision.REVISE,
        edited_plan_text="- Step 1\n- Step 2",
    )

    assert approve.decision == MagenticPlanReviewDecision.APPROVE
    assert revise_comments.comments == "Tighten scope"
    assert revise_text.edited_plan_text is not None and revise_text.edited_plan_text.startswith("- Step 1")


def test_magentic_context_reset_behavior():
    ctx = MagenticContext(
        task=ChatMessage(role=Role.USER, text="task"),
        participant_descriptions={"Alice": "Researcher"},
    )
    # seed context state
    ctx.chat_history.append(ChatMessage(role=Role.ASSISTANT, text="draft"))
    ctx.stall_count = 2
    prev_reset = ctx.reset_count

    ctx.reset()

    assert ctx.chat_history == []
    assert ctx.stall_count == 0
    assert ctx.reset_count == prev_reset + 1


@dataclass
class _SimpleLedger:
    facts: ChatMessage
    plan: ChatMessage


class FakeManager(MagenticManagerBase):
    """Deterministic manager for tests that avoids real LLM calls."""

    task_ledger: _SimpleLedger | None = None
    satisfied_after_signoff: bool = True
    next_speaker_name: str = "agentA"
    instruction_text: str = "Proceed with step 1"

    async def plan(self, magentic_context: MagenticContext) -> ChatMessage:
        facts = ChatMessage(role=Role.ASSISTANT, text="GIVEN OR VERIFIED FACTS\n- A\n")
        plan = ChatMessage(role=Role.ASSISTANT, text="- Do X\n- Do Y\n")
        self.task_ledger = _SimpleLedger(facts=facts, plan=plan)
        combined = f"Task: {magentic_context.task.text}\n\nFacts:\n{facts.text}\n\nPlan:\n{plan.text}"
        return ChatMessage(role=Role.ASSISTANT, text=combined, author_name="magentic_manager")

    async def replan(self, magentic_context: MagenticContext) -> ChatMessage:
        facts = ChatMessage(role=Role.ASSISTANT, text="GIVEN OR VERIFIED FACTS\n- A2\n")
        plan = ChatMessage(role=Role.ASSISTANT, text="- Do Z\n")
        self.task_ledger = _SimpleLedger(facts=facts, plan=plan)
        combined = f"Task: {magentic_context.task.text}\n\nFacts:\n{facts.text}\n\nPlan:\n{plan.text}"
        return ChatMessage(role=Role.ASSISTANT, text=combined, author_name="magentic_manager")

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
        is_satisfied = self.satisfied_after_signoff and len(magentic_context.chat_history) > 0
        return MagenticProgressLedger(
            is_request_satisfied=MagenticProgressLedgerItem(reason="test", answer=is_satisfied),
            is_in_loop=MagenticProgressLedgerItem(reason="test", answer=False),
            is_progress_being_made=MagenticProgressLedgerItem(reason="test", answer=True),
            next_speaker=MagenticProgressLedgerItem(reason="test", answer=self.next_speaker_name),
            instruction_or_question=MagenticProgressLedgerItem(reason="test", answer=self.instruction_text),
        )

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> ChatMessage:
        return ChatMessage(role=Role.ASSISTANT, text="FINAL", author_name="magentic_manager")


async def test_standard_manager_plan_and_replan_combined_ledger():
    manager = FakeManager(max_round_count=10, max_stall_count=3, max_reset_count=2)
    ctx = MagenticContext(
        task=ChatMessage(role=Role.USER, text="demo task"),
        participant_descriptions={"agentA": "Agent A"},
    )

    first = await manager.plan(ctx.model_copy(deep=True))
    assert first.role == Role.ASSISTANT and "Facts:" in first.text and "Plan:" in first.text
    assert manager.task_ledger is not None

    replanned = await manager.replan(ctx.model_copy(deep=True))
    assert "A2" in replanned.text or "Do Z" in replanned.text


async def test_standard_manager_progress_ledger_and_fallback():
    manager = FakeManager(max_round_count=10)
    ctx = MagenticContext(
        task=ChatMessage(role=Role.USER, text="demo"),
        participant_descriptions={"agentA": "Agent A"},
    )

    ledger = await manager.create_progress_ledger(ctx.model_copy(deep=True))
    assert isinstance(ledger, MagenticProgressLedger)
    assert ledger.next_speaker.answer == "agentA"

    manager.satisfied_after_signoff = False
    ledger2 = await manager.create_progress_ledger(ctx.model_copy(deep=True))
    assert ledger2.is_request_satisfied.answer is False


async def test_magentic_workflow_plan_review_approval_to_completion():
    manager = FakeManager(max_round_count=10)
    wf = (
        MagenticBuilder()
        .participants(agentA=_DummyExec("agentA"))
        .with_standard_manager(manager)
        .with_plan_review()
        .build()
    )

    req_event: RequestInfoEvent | None = None
    async for ev in wf.run_stream("do work"):
        if isinstance(ev, RequestInfoEvent) and ev.request_type is MagenticPlanReviewRequest:
            req_event = ev
    assert req_event is not None

    completed = False
    output: ChatMessage | None = None
    async for ev in wf.send_responses_streaming({
        req_event.request_id: MagenticPlanReviewReply(decision=MagenticPlanReviewDecision.APPROVE)
    }):
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif isinstance(ev, WorkflowOutputEvent):
            output = ev.data  # type: ignore[assignment]
        if completed and output is not None:
            break
    assert completed
    assert output is not None
    assert isinstance(output, ChatMessage)


async def test_magentic_plan_review_approve_with_comments_replans_and_proceeds():
    class CountingManager(FakeManager):
        # Declare as a model field so assignment is allowed under Pydantic
        replan_count: int = 0

        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            super().__init__(*args, **kwargs)

        async def replan(self, magentic_context: MagenticContext) -> ChatMessage:  # type: ignore[override]
            self.replan_count += 1
            return await super().replan(magentic_context)

    manager = CountingManager(max_round_count=10)
    wf = (
        MagenticBuilder()
        .participants(agentA=_DummyExec("agentA"))
        .with_standard_manager(manager)
        .with_plan_review()
        .build()
    )

    # Wait for the initial plan review request
    req_event: RequestInfoEvent | None = None
    async for ev in wf.run_stream("do work"):
        if isinstance(ev, RequestInfoEvent) and ev.request_type is MagenticPlanReviewRequest:
            req_event = ev
    assert req_event is not None

    # Reply APPROVE with comments (no edited text). Expect one replan and no second review round.
    saw_second_review = False
    completed = False
    async for ev in wf.send_responses_streaming({
        req_event.request_id: MagenticPlanReviewReply(
            decision=MagenticPlanReviewDecision.APPROVE,
            comments="Looks good; consider Z",
        )
    }):
        if isinstance(ev, RequestInfoEvent) and ev.request_type is MagenticPlanReviewRequest:
            saw_second_review = True
        if isinstance(ev, WorkflowStatusEvent) and ev.state == WorkflowRunState.IDLE:
            completed = True
            break

    assert completed
    assert manager.replan_count >= 1
    assert saw_second_review is False
    # Replan from FakeManager updates facts/plan to include A2 / Do Z
    assert manager.task_ledger is not None
    combined_text = (manager.task_ledger.facts.text or "") + (manager.task_ledger.plan.text or "")
    assert ("A2" in combined_text) or ("Do Z" in combined_text)


async def test_magentic_orchestrator_round_limit_produces_partial_result():
    manager = FakeManager(max_round_count=1)
    manager.satisfied_after_signoff = False
    wf = MagenticBuilder().participants(agentA=_DummyExec("agentA")).with_standard_manager(manager).build()

    from agent_framework import WorkflowEvent  # type: ignore

    events: list[WorkflowEvent] = []
    async for ev in wf.run_stream("round limit test"):
        events.append(ev)
        if len(events) > 50:
            break

    idle_status = next(
        (e for e in events if isinstance(e, WorkflowStatusEvent) and e.state == WorkflowRunState.IDLE), None
    )
    assert idle_status is not None
    # Check that we got workflow output via WorkflowOutputEvent
    output_event = next((e for e in events if isinstance(e, WorkflowOutputEvent)), None)
    assert output_event is not None
    data = output_event.data
    assert isinstance(data, ChatMessage)
    assert data.role == Role.ASSISTANT


class _DummyExec(Executor):
    def __init__(self, name: str) -> None:
        super().__init__(name)

    @handler
    async def _noop(self, message: object, ctx: WorkflowContext[object]) -> None:  # pragma: no cover - not called
        pass


from agent_framework import StandardMagenticManager  # noqa: E402


class _StubChatClient(AFChatClient):
    async def get_response(self, messages, **kwargs):  # type: ignore[override]
        return ChatResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="ok")])

    def get_streaming_response(self, messages, **kwargs) -> AsyncIterable[ChatResponseUpdate]:  # type: ignore[override]
        async def _gen():
            if False:
                yield ChatResponseUpdate()  # pragma: no cover

        return _gen()


async def test_standard_manager_plan_and_replan_via_complete_monkeypatch():
    mgr = StandardMagenticManager(chat_client=_StubChatClient())

    async def fake_complete_plan(messages: list[ChatMessage], **kwargs: Any) -> ChatMessage:
        # Return a different response depending on call order length
        if any("FACTS" in (m.text or "") for m in messages):
            return ChatMessage(role=Role.ASSISTANT, text="- step A\n- step B")
        return ChatMessage(role=Role.ASSISTANT, text="GIVEN OR VERIFIED FACTS\n- fact1")

    # First, patch to produce facts then plan
    mgr._complete = fake_complete_plan  # type: ignore[attr-defined]

    ctx = MagenticContext(
        task=ChatMessage(role=Role.USER, text="T"),
        participant_descriptions={"A": "desc"},
    )
    combined = await mgr.plan(ctx.model_copy(deep=True))
    # Assert structural headings and that steps appear in the combined ledger output.
    assert "We are working to address the following user request:" in combined.text
    assert "Here is the plan to follow as best as possible:" in combined.text
    assert any(t in combined.text for t in ("- step A", "- step B", "- step"))

    # Now replan with new outputs
    async def fake_complete_replan(messages: list[ChatMessage], **kwargs: Any) -> ChatMessage:
        if any("Please briefly explain" in (m.text or "") for m in messages):
            return ChatMessage(role=Role.ASSISTANT, text="- new step")
        return ChatMessage(role=Role.ASSISTANT, text="GIVEN OR VERIFIED FACTS\n- updated")

    mgr._complete = fake_complete_replan  # type: ignore[attr-defined]
    combined2 = await mgr.replan(ctx.model_copy(deep=True))
    assert "updated" in combined2.text or "new step" in combined2.text


async def test_standard_manager_progress_ledger_success_and_error():
    mgr = StandardMagenticManager(chat_client=_StubChatClient())
    ctx = MagenticContext(
        task=ChatMessage(role=Role.USER, text="task"),
        participant_descriptions={"alice": "desc"},
    )

    # Success path: valid JSON
    async def fake_complete_ok(messages: list[ChatMessage], **kwargs: Any) -> ChatMessage:
        json_text = (
            '{"is_request_satisfied": {"reason": "r", "answer": false}, '
            '"is_in_loop": {"reason": "r", "answer": false}, '
            '"is_progress_being_made": {"reason": "r", "answer": true}, '
            '"next_speaker": {"reason": "r", "answer": "alice"}, '
            '"instruction_or_question": {"reason": "r", "answer": "do"}}'
        )
        return ChatMessage(role=Role.ASSISTANT, text=json_text)

    mgr._complete = fake_complete_ok  # type: ignore[attr-defined]
    ledger = await mgr.create_progress_ledger(ctx.model_copy(deep=True))
    assert ledger.next_speaker.answer == "alice"

    # Error path: invalid JSON now raises to avoid emitting planner-oriented instructions to agents
    async def fake_complete_bad(messages: list[ChatMessage], **kwargs: Any) -> ChatMessage:
        return ChatMessage(role=Role.ASSISTANT, text="not-json")

    mgr._complete = fake_complete_bad  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError):
        await mgr.create_progress_ledger(ctx.model_copy(deep=True))


class InvokeOnceManager(MagenticManagerBase):
    def __init__(self) -> None:
        super().__init__(max_round_count=5, max_stall_count=3, max_reset_count=2)
        self._invoked = False

    async def plan(self, magentic_context: MagenticContext) -> ChatMessage:
        return ChatMessage(role=Role.ASSISTANT, text="ledger")

    async def replan(self, magentic_context: MagenticContext) -> ChatMessage:
        return ChatMessage(role=Role.ASSISTANT, text="re-ledger")

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
        if not self._invoked:
            # First round: ask agentA to respond
            self._invoked = True
            return MagenticProgressLedger(
                is_request_satisfied=MagenticProgressLedgerItem(reason="r", answer=False),
                is_in_loop=MagenticProgressLedgerItem(reason="r", answer=False),
                is_progress_being_made=MagenticProgressLedgerItem(reason="r", answer=True),
                next_speaker=MagenticProgressLedgerItem(reason="r", answer="agentA"),
                instruction_or_question=MagenticProgressLedgerItem(reason="r", answer="say hi"),
            )
        # Next round: mark satisfied so run can conclude
        return MagenticProgressLedger(
            is_request_satisfied=MagenticProgressLedgerItem(reason="r", answer=True),
            is_in_loop=MagenticProgressLedgerItem(reason="r", answer=False),
            is_progress_being_made=MagenticProgressLedgerItem(reason="r", answer=True),
            next_speaker=MagenticProgressLedgerItem(reason="r", answer="agentA"),
            instruction_or_question=MagenticProgressLedgerItem(reason="r", answer="done"),
        )

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> ChatMessage:
        return ChatMessage(role=Role.ASSISTANT, text="final")


class StubThreadAgent(BaseAgent):
    async def run_stream(self, messages=None, *, thread=None, **kwargs):  # type: ignore[override]
        yield AgentRunResponseUpdate(
            contents=[TextContent(text="thread-ok")],
            author_name="agentA",
            role=Role.ASSISTANT,
        )

    async def run(self, messages=None, *, thread=None, **kwargs):  # type: ignore[override]
        return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="thread-ok", author_name="agentA")])


class StubAssistantsClient:
    pass  # class name used for branch detection


class StubAssistantsAgent(BaseAgent):
    chat_client: object | None = None  # allow assignment via Pydantic field

    def __init__(self) -> None:
        super().__init__()
        self.chat_client = StubAssistantsClient()  # type name contains 'AssistantsClient'

    async def run_stream(self, messages=None, *, thread=None, **kwargs):  # type: ignore[override]
        yield AgentRunResponseUpdate(
            contents=[TextContent(text="assistants-ok")],
            author_name="agentA",
            role=Role.ASSISTANT,
        )

    async def run(self, messages=None, *, thread=None, **kwargs):  # type: ignore[override]
        return AgentRunResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="assistants-ok", author_name="agentA")])


async def _collect_agent_responses_setup(participant_obj: object):
    captured: list[ChatMessage] = []

    async def sink(event) -> None:  # type: ignore[no-untyped-def]
        from agent_framework._workflow._magentic import MagenticAgentMessageEvent

        if isinstance(event, MagenticAgentMessageEvent) and event.message is not None:
            captured.append(event.message)

    wf = (
        MagenticBuilder()
        .participants(agentA=participant_obj)  # type: ignore[arg-type]
        .with_standard_manager(InvokeOnceManager())
        .on_event(sink)  # type: ignore
        .build()
    )

    # Run a bounded stream to allow one invoke and then completion
    events: list[WorkflowEvent] = []
    async for ev in wf.run_stream("task"):  # plan review disabled
        events.append(ev)
        if len(events) > 50:
            break

    return captured


async def test_agent_executor_invoke_with_thread_chat_client():
    captured = await _collect_agent_responses_setup(StubThreadAgent())
    # Should have at least one response from agentA via MagenticAgentExecutor path
    assert any((m.author_name == "agentA" and "ok" in (m.text or "")) for m in captured)


async def test_agent_executor_invoke_with_assistants_client_messages():
    captured = await _collect_agent_responses_setup(StubAssistantsAgent())
    assert any((m.author_name == "agentA" and "ok" in (m.text or "")) for m in captured)
