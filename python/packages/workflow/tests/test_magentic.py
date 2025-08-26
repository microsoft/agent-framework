# Copyright (c) Microsoft. All rights reserved.

from collections.abc import AsyncIterable
from dataclasses import dataclass

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatMessage,
    ChatResponse,
    ChatResponseUpdate,
    ChatRole,
    TextContent,
)
from agent_framework._agents import AgentBase
from agent_framework._clients import ChatClient as AFChatClient

from agent_framework_workflow import (
    Executor,
    MagenticManagerBase,
    MagenticWorkflowBuilder,
    ProgressLedger,
    ProgressLedgerItem,
    RequestInfoEvent,
    WorkflowCompletedEvent,
    WorkflowContext,
    WorkflowEvent,  # type: ignore  # noqa: E402
    handler,
)
from agent_framework_workflow._magentic import (
    MagenticContext,
    MagenticResetMessage,
    MagenticStartMessage,
    PlanReviewDecision,
    PlanReviewReply,
    PlanReviewRequest,
)


def test_magentic_start_message_from_string():
    msg = MagenticStartMessage.from_string("Do the thing")
    assert isinstance(msg, MagenticStartMessage)
    assert isinstance(msg.task, ChatMessage)
    assert msg.task.role == ChatRole.USER
    assert msg.task.text == "Do the thing"


def test_plan_review_request_defaults_and_reply_variants():
    req = PlanReviewRequest()  # defaults provided by dataclass
    assert hasattr(req, "request_id")
    assert req.task_text == "" and req.facts_text == "" and req.plan_text == ""
    assert isinstance(req.round_index, int) and req.round_index == 0

    # Replies: approve, revise with comments, revise with edited text
    approve = PlanReviewReply(decision=PlanReviewDecision.APPROVE)
    revise_comments = PlanReviewReply(decision=PlanReviewDecision.REVISE, comments="Tighten scope")
    revise_text = PlanReviewReply(
        decision=PlanReviewDecision.REVISE,
        edited_plan_text="- Step 1\n- Step 2",
    )

    assert approve.decision == PlanReviewDecision.APPROVE
    assert revise_comments.comments == "Tighten scope"
    assert revise_text.edited_plan_text is not None and revise_text.edited_plan_text.startswith("- Step 1")


def test_magentic_context_reset_behavior():
    ctx = MagenticContext(
        task=ChatMessage(role=ChatRole.USER, text="task"),
        participant_descriptions={"Alice": "Researcher"},
    )
    # seed context state
    ctx.chat_history.append(ChatMessage(role=ChatRole.ASSISTANT, text="draft"))
    ctx.stall_count = 2
    prev_reset = ctx.reset_count

    ctx.reset()

    assert ctx.chat_history == []
    assert ctx.stall_count == 0
    assert ctx.reset_count == prev_reset + 1


def test_magentic_reset_message_instantiation():
    reset_msg = MagenticResetMessage()
    assert isinstance(reset_msg, MagenticResetMessage)


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
        facts = ChatMessage(role=ChatRole.ASSISTANT, text="GIVEN OR VERIFIED FACTS\n- A\n")
        plan = ChatMessage(role=ChatRole.ASSISTANT, text="- Do X\n- Do Y\n")
        self.task_ledger = _SimpleLedger(facts=facts, plan=plan)
        combined = f"Task: {magentic_context.task.text}\n\nFacts:\n{facts.text}\n\nPlan:\n{plan.text}"
        return ChatMessage(role=ChatRole.ASSISTANT, text=combined, author_name="magentic_manager")

    async def replan(self, magentic_context: MagenticContext) -> ChatMessage:
        facts = ChatMessage(role=ChatRole.ASSISTANT, text="GIVEN OR VERIFIED FACTS\n- A2\n")
        plan = ChatMessage(role=ChatRole.ASSISTANT, text="- Do Z\n")
        self.task_ledger = _SimpleLedger(facts=facts, plan=plan)
        combined = f"Task: {magentic_context.task.text}\n\nFacts:\n{facts.text}\n\nPlan:\n{plan.text}"
        return ChatMessage(role=ChatRole.ASSISTANT, text=combined, author_name="magentic_manager")

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> ProgressLedger:
        is_satisfied = self.satisfied_after_signoff and len(magentic_context.chat_history) > 0
        return ProgressLedger(
            is_request_satisfied=ProgressLedgerItem(reason="test", answer=is_satisfied),
            is_in_loop=ProgressLedgerItem(reason="test", answer=False),
            is_progress_being_made=ProgressLedgerItem(reason="test", answer=True),
            next_speaker=ProgressLedgerItem(reason="test", answer=self.next_speaker_name),
            instruction_or_question=ProgressLedgerItem(reason="test", answer=self.instruction_text),
        )

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> ChatMessage:
        return ChatMessage(role=ChatRole.ASSISTANT, text="FINAL", author_name="magentic_manager")


async def test_standard_manager_plan_and_replan_combined_ledger():
    manager = FakeManager(max_round_count=10, max_stall_count=3, max_reset_count=2)
    ctx = MagenticContext(
        task=ChatMessage(role=ChatRole.USER, text="demo task"),
        participant_descriptions={"agentA": "Agent A"},
    )

    first = await manager.plan(ctx.model_copy(deep=True))
    assert first.role == ChatRole.ASSISTANT and "Facts:" in first.text and "Plan:" in first.text
    assert manager.task_ledger is not None

    replanned = await manager.replan(ctx.model_copy(deep=True))
    assert "A2" in replanned.text or "Do Z" in replanned.text


async def test_standard_manager_progress_ledger_and_fallback():
    manager = FakeManager(max_round_count=10)
    ctx = MagenticContext(
        task=ChatMessage(role=ChatRole.USER, text="demo"),
        participant_descriptions={"agentA": "Agent A"},
    )

    ledger = await manager.create_progress_ledger(ctx.model_copy(deep=True))
    assert isinstance(ledger, ProgressLedger)
    assert ledger.next_speaker.answer == "agentA"

    manager.satisfied_after_signoff = False
    ledger2 = await manager.create_progress_ledger(ctx.model_copy(deep=True))
    assert ledger2.is_request_satisfied.answer is False


async def test_magentic_workflow_plan_review_approval_to_completion():
    manager = FakeManager(max_round_count=10)
    wf = (
        MagenticWorkflowBuilder()
        .participants(agentA=_DummyExec("agentA"))
        .with_manager(manager)
        .with_plan_review()
        .build()
    )

    req_event: RequestInfoEvent | None = None
    async for ev in wf.run_streaming("do work"):
        if isinstance(ev, RequestInfoEvent) and ev.request_type is PlanReviewRequest:
            req_event = ev
    assert req_event is not None

    completed: WorkflowCompletedEvent | None = None
    async for ev in wf.send_responses_streaming({
        req_event.request_id: PlanReviewReply(decision=PlanReviewDecision.APPROVE)
    }):
        if isinstance(ev, WorkflowCompletedEvent):
            completed = ev
            break
    assert completed is not None
    assert isinstance(getattr(completed, "data", None), ChatMessage)


async def test_magentic_orchestrator_round_limit_produces_partial_result():
    manager = FakeManager(max_round_count=1)
    manager.satisfied_after_signoff = False
    wf = MagenticWorkflowBuilder().participants(agentA=_DummyExec("agentA")).with_manager(manager).build()

    from agent_framework_workflow import WorkflowEvent  # type: ignore

    events: list[WorkflowEvent] = []
    async for ev in wf.run_streaming("round limit test"):
        events.append(ev)
        if len(events) > 50:
            break

    completed = next((e for e in events if isinstance(e, WorkflowCompletedEvent)), None)
    assert completed is not None
    data = getattr(completed, "data", None)
    assert isinstance(data, ChatMessage)
    assert data.role == ChatRole.ASSISTANT


class _DummyExec(Executor):
    def __init__(self, name: str) -> None:
        super().__init__(name)

    @handler
    async def _noop(self, message: object, ctx: WorkflowContext[object]) -> None:  # pragma: no cover - not called
        pass


from agent_framework_workflow import StandardMagenticManager  # noqa: E402


class _StubChatClient(AFChatClient):
    async def get_response(self, messages, **kwargs):  # type: ignore[override]
        return ChatResponse(messages=[ChatMessage(role=ChatRole.ASSISTANT, text="ok")])

    def get_streaming_response(self, messages, **kwargs) -> AsyncIterable[ChatResponseUpdate]:  # type: ignore[override]
        async def _gen():
            if False:
                yield ChatResponseUpdate()  # pragma: no cover

        return _gen()


async def test_standard_manager_plan_and_replan_via_complete_monkeypatch():
    mgr = StandardMagenticManager(chat_client=_StubChatClient())

    async def fake_complete_plan(messages: list[ChatMessage]) -> ChatMessage:
        # Return a different response depending on call order length
        if any("FACTS" in (m.text or "") for m in messages):
            return ChatMessage(role=ChatRole.ASSISTANT, text="- step A\n- step B")
        return ChatMessage(role=ChatRole.ASSISTANT, text="GIVEN OR VERIFIED FACTS\n- fact1")

    # First, patch to produce facts then plan
    mgr._complete = fake_complete_plan  # type: ignore[attr-defined]

    ctx = MagenticContext(
        task=ChatMessage(role=ChatRole.USER, text="T"),
        participant_descriptions={"A": "desc"},
    )
    combined = await mgr.plan(ctx.model_copy(deep=True))
    # Assert structural headings and that steps appear in the combined ledger output.
    assert "We are working to address the following user request:" in combined.text
    assert "Here is the plan to follow as best as possible:" in combined.text
    assert any(t in combined.text for t in ("- step A", "- step B", "- step"))

    # Now replan with new outputs
    async def fake_complete_replan(messages: list[ChatMessage]) -> ChatMessage:
        if any("Please briefly explain" in (m.text or "") for m in messages):
            return ChatMessage(role=ChatRole.ASSISTANT, text="- new step")
        return ChatMessage(role=ChatRole.ASSISTANT, text="GIVEN OR VERIFIED FACTS\n- updated")

    mgr._complete = fake_complete_replan  # type: ignore[attr-defined]
    combined2 = await mgr.replan(ctx.model_copy(deep=True))
    assert "updated" in combined2.text or "new step" in combined2.text


async def test_standard_manager_progress_ledger_success_and_fallback():
    mgr = StandardMagenticManager(chat_client=_StubChatClient())
    ctx = MagenticContext(
        task=ChatMessage(role=ChatRole.USER, text="task"),
        participant_descriptions={"alice": "desc"},
    )

    # Success path: valid JSON
    async def fake_complete_ok(messages: list[ChatMessage]) -> ChatMessage:
        json_text = (
            '{"is_request_satisfied": {"reason": "r", "answer": false}, '
            '"is_in_loop": {"reason": "r", "answer": false}, '
            '"is_progress_being_made": {"reason": "r", "answer": true}, '
            '"next_speaker": {"reason": "r", "answer": "alice"}, '
            '"instruction_or_question": {"reason": "r", "answer": "do"}}'
        )
        return ChatMessage(role=ChatRole.ASSISTANT, text=json_text)

    mgr._complete = fake_complete_ok  # type: ignore[attr-defined]
    ledger = await mgr.create_progress_ledger(ctx.model_copy(deep=True))
    assert ledger.next_speaker.answer == "alice"

    # Fallback path: invalid JSON triggers default ledger
    async def fake_complete_bad(messages: list[ChatMessage]) -> ChatMessage:
        return ChatMessage(role=ChatRole.ASSISTANT, text="not-json")

    mgr._complete = fake_complete_bad  # type: ignore[attr-defined]
    ledger2 = await mgr.create_progress_ledger(ctx.model_copy(deep=True))
    assert ledger2.is_request_satisfied.answer is False
    assert isinstance(ledger2.instruction_or_question.answer, str)


class InvokeOnceManager(MagenticManagerBase):
    def __init__(self) -> None:
        super().__init__(max_round_count=5, max_stall_count=3, max_reset_count=2)
        self._invoked = False

    async def plan(self, magentic_context: MagenticContext) -> ChatMessage:
        return ChatMessage(role=ChatRole.ASSISTANT, text="ledger")

    async def replan(self, magentic_context: MagenticContext) -> ChatMessage:
        return ChatMessage(role=ChatRole.ASSISTANT, text="re-ledger")

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> ProgressLedger:
        if not self._invoked:
            # First round: ask agentA to respond
            self._invoked = True
            return ProgressLedger(
                is_request_satisfied=ProgressLedgerItem(reason="r", answer=False),
                is_in_loop=ProgressLedgerItem(reason="r", answer=False),
                is_progress_being_made=ProgressLedgerItem(reason="r", answer=True),
                next_speaker=ProgressLedgerItem(reason="r", answer="agentA"),
                instruction_or_question=ProgressLedgerItem(reason="r", answer="say hi"),
            )
        # Next round: mark satisfied so run can conclude
        return ProgressLedger(
            is_request_satisfied=ProgressLedgerItem(reason="r", answer=True),
            is_in_loop=ProgressLedgerItem(reason="r", answer=False),
            is_progress_being_made=ProgressLedgerItem(reason="r", answer=True),
            next_speaker=ProgressLedgerItem(reason="r", answer="agentA"),
            instruction_or_question=ProgressLedgerItem(reason="r", answer="done"),
        )

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> ChatMessage:
        return ChatMessage(role=ChatRole.ASSISTANT, text="final")


class StubThreadAgent(AgentBase):
    async def run_streaming(self, messages=None, *, thread=None, **kwargs):  # type: ignore[override]
        yield AgentRunResponseUpdate(
            contents=[TextContent(text="thread-ok")],
            author_name="agentA",
            role=ChatRole.ASSISTANT,
        )

    async def run(self, messages=None, *, thread=None, **kwargs):  # type: ignore[override]
        return AgentRunResponse(messages=[ChatMessage(role=ChatRole.ASSISTANT, text="thread-ok", author_name="agentA")])


class StubAssistantsClient:
    pass  # class name used for branch detection


class StubAssistantsAgent(AgentBase):
    chat_client: object | None = None  # allow assignment via Pydantic field

    def __init__(self) -> None:
        super().__init__()
        self.chat_client = StubAssistantsClient()  # type name contains 'AssistantsClient'

    async def run_streaming(self, messages=None, *, thread=None, **kwargs):  # type: ignore[override]
        yield AgentRunResponseUpdate(
            contents=[TextContent(text="assistants-ok")],
            author_name="agentA",
            role=ChatRole.ASSISTANT,
        )

    async def run(self, messages=None, *, thread=None, **kwargs):  # type: ignore[override]
        return AgentRunResponse(
            messages=[ChatMessage(role=ChatRole.ASSISTANT, text="assistants-ok", author_name="agentA")]
        )


async def _collect_agent_responses_setup(participant_obj: object):
    captured: list[ChatMessage] = []

    wf = (
        MagenticWorkflowBuilder()
        .participants(agentA=participant_obj)  # type: ignore[arg-type]
        .with_manager(InvokeOnceManager())
        .on_agent_response(lambda agent_id, msg: (captured.append(msg)) and (None))  # type: ignore[arg-type]
        .build()
    )

    # Run a bounded stream to allow one invoke and then completion
    events: list[WorkflowEvent] = []
    async for ev in wf.run_streaming("task"):  # plan review disabled
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
