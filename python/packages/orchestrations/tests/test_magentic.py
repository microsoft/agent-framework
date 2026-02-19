# Copyright (c) Microsoft. All rights reserved.

import sys
from collections.abc import AsyncIterable, Awaitable, Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, cast

import pytest
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    AgentSession,
    BaseAgent,
    Content,
    Executor,
    Message,
    SupportsAgentRun,
    Workflow,
    WorkflowCheckpoint,
    WorkflowCheckpointException,
    WorkflowContext,
    WorkflowEvent,
    WorkflowRunState,
    handler,
)
from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage
from agent_framework.orchestrations import (
    GroupChatRequestMessage,
    MagenticBuilder,
    MagenticContext,
    MagenticManagerBase,
    MagenticOrchestrator,
    MagenticPlanReviewRequest,
    MagenticProgressLedger,
    MagenticProgressLedgerItem,
    StandardMagenticManager,
)

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover


def test_magentic_context_reset_behavior():
    ctx = MagenticContext(
        task="task",
        participant_descriptions={"Alice": "Researcher"},
    )
    # seed context state
    ctx.chat_history.append(Message("assistant", ["draft"]))
    ctx.stall_count = 2
    prev_reset = ctx.reset_count

    ctx.reset()

    assert ctx.chat_history == []
    assert ctx.stall_count == 0
    assert ctx.reset_count == prev_reset + 1


@dataclass
class _SimpleLedger:
    facts: Message
    plan: Message


class FakeManager(MagenticManagerBase):
    """Deterministic manager for tests that avoids real LLM calls."""

    FINAL_ANSWER: ClassVar[str] = "FINAL"

    def __init__(
        self,
        *,
        max_stall_count: int = 3,
        max_reset_count: int | None = None,
        max_round_count: int | None = None,
    ) -> None:
        super().__init__(
            max_stall_count=max_stall_count,
            max_reset_count=max_reset_count,
            max_round_count=max_round_count,
        )
        self.name = "magentic_manager"
        self.task_ledger: _SimpleLedger | None = None
        self.next_speaker_name: str = "agentA"
        self.instruction_text: str = "Proceed with step 1"

    @override
    def on_checkpoint_save(self) -> dict[str, Any]:
        state = super().on_checkpoint_save()
        if self.task_ledger is not None:
            state = dict(state)
            state["task_ledger"] = {
                "facts": self.task_ledger.facts.to_dict(),
                "plan": self.task_ledger.plan.to_dict(),
            }
        return state

    @override
    def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        super().on_checkpoint_restore(state)
        ledger_state = state.get("task_ledger")
        if isinstance(ledger_state, dict):
            ledger_dict = cast(dict[str, Any], ledger_state)
            facts_payload = cast(dict[str, Any] | None, ledger_dict.get("facts"))
            plan_payload = cast(dict[str, Any] | None, ledger_dict.get("plan"))
            if facts_payload is not None and plan_payload is not None:
                try:
                    facts = Message.from_dict(facts_payload)
                    plan = Message.from_dict(plan_payload)
                    self.task_ledger = _SimpleLedger(facts=facts, plan=plan)
                except Exception:  # pragma: no cover - defensive
                    pass

    async def plan(self, magentic_context: MagenticContext) -> Message:
        facts = Message("assistant", ["GIVEN OR VERIFIED FACTS\n- A\n"])
        plan = Message("assistant", ["- Do X\n- Do Y\n"])
        self.task_ledger = _SimpleLedger(facts=facts, plan=plan)
        combined = f"Task: {magentic_context.task}\n\nFacts:\n{facts.text}\n\nPlan:\n{plan.text}"
        return Message("assistant", [combined], author_name=self.name)

    async def replan(self, magentic_context: MagenticContext) -> Message:
        facts = Message("assistant", ["GIVEN OR VERIFIED FACTS\n- A2\n"])
        plan = Message("assistant", ["- Do Z\n"])
        self.task_ledger = _SimpleLedger(facts=facts, plan=plan)
        combined = f"Task: {magentic_context.task}\n\nFacts:\n{facts.text}\n\nPlan:\n{plan.text}"
        return Message("assistant", [combined], author_name=self.name)

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
        # At least two messages in chat history means request is satisfied for testing
        is_satisfied = len(magentic_context.chat_history) > 1
        return MagenticProgressLedger(
            is_request_satisfied=MagenticProgressLedgerItem(reason="test", answer=is_satisfied),
            is_in_loop=MagenticProgressLedgerItem(reason="test", answer=False),
            is_progress_being_made=MagenticProgressLedgerItem(reason="test", answer=True),
            next_speaker=MagenticProgressLedgerItem(reason="test", answer=self.next_speaker_name),
            instruction_or_question=MagenticProgressLedgerItem(reason="test", answer=self.instruction_text),
        )

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> Message:
        return Message("assistant", [self.FINAL_ANSWER], author_name=self.name)


class StubAgent(BaseAgent):
    def __init__(self, agent_name: str, reply_text: str, **kwargs: Any) -> None:
        super().__init__(name=agent_name, description=f"Stub agent {agent_name}", **kwargs)
        self._reply_text = reply_text

    def run(  # type: ignore[override]
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: AgentSession | None = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | AsyncIterable[AgentResponseUpdate]:
        if stream:
            return self._run_stream()

        async def _run() -> AgentResponse:
            response = Message("assistant", [self._reply_text], author_name=self.name)
            return AgentResponse(messages=[response])

        return _run()

    async def _run_stream(self) -> AsyncIterable[AgentResponseUpdate]:
        yield AgentResponseUpdate(
            contents=[Content.from_text(text=self._reply_text)], role="assistant", author_name=self.name
        )


class DummyExec(Executor):
    def __init__(self, name: str) -> None:
        super().__init__(name)

    @handler
    async def _noop(
        self, message: GroupChatRequestMessage, ctx: WorkflowContext[Message]
    ) -> None:  # pragma: no cover - not called
        pass


async def test_magentic_builder_returns_workflow_and_runs() -> None:
    manager = FakeManager()
    agent = StubAgent(manager.next_speaker_name, "first draft")

    workflow = MagenticBuilder(participants=[agent], manager=manager).build()

    assert isinstance(workflow, Workflow)

    outputs: list[Message] = []
    orchestrator_event_count = 0
    async for event in workflow.run("compose summary", stream=True):
        if event.type == "output":
            msg = event.data
            if isinstance(msg, list):
                outputs.extend(cast(list[Message], msg))
        elif event.type == "magentic_orchestrator":
            orchestrator_event_count += 1

    assert outputs, "Expected a final output message"
    assert len(outputs) >= 1
    final = outputs[-1]
    assert final.text == manager.FINAL_ANSWER
    assert final.author_name == manager.name
    assert orchestrator_event_count > 0, "Expected orchestrator events to be emitted"


async def test_magentic_as_agent_does_not_accept_conversation() -> None:
    manager = FakeManager()
    writer = StubAgent(manager.next_speaker_name, "summary response")

    workflow = MagenticBuilder(participants=[writer], manager=manager).build()

    agent = workflow.as_agent(name="magentic-agent")
    conversation = [
        Message("system", ["Guidelines"], author_name="system"),
        Message("user", ["Summarize the findings"], author_name="requester"),
    ]
    with pytest.raises(ValueError, match="Magentic only support a single task message to start the workflow."):
        await agent.run(conversation)


async def test_standard_manager_plan_and_replan_combined_ledger():
    manager = FakeManager()
    ctx = MagenticContext(
        task="demo task",
        participant_descriptions={"agentA": "Agent A"},
    )

    first = await manager.plan(ctx.clone())
    assert first.role == "assistant" and "Facts:" in first.text and "Plan:" in first.text
    assert manager.task_ledger is not None

    replanned = await manager.replan(ctx.clone())
    assert "A2" in replanned.text or "Do Z" in replanned.text


async def test_magentic_workflow_plan_review_approval_to_completion():
    manager = FakeManager()
    wf = MagenticBuilder(participants=[DummyExec("agentA")], enable_plan_review=True, manager=manager).build()

    req_event: WorkflowEvent | None = None
    async for ev in wf.run("do work", stream=True):
        if ev.type == "request_info" and ev.request_type is MagenticPlanReviewRequest:
            req_event = ev
    assert req_event is not None
    assert isinstance(req_event.data, MagenticPlanReviewRequest)

    completed = False
    output: list[Message] | None = None
    async for ev in wf.run(stream=True, responses={req_event.request_id: req_event.data.approve()}):
        if ev.type == "status" and ev.state == WorkflowRunState.IDLE:
            completed = True
        elif ev.type == "output":
            output = ev.data  # type: ignore[assignment]
        if completed and output is not None:
            break

    assert completed
    assert output is not None
    assert isinstance(output, list)
    assert all(isinstance(msg, Message) for msg in output)


async def test_magentic_plan_review_with_revise():
    class CountingManager(FakeManager):
        # Declare as a model field so assignment is allowed under Pydantic
        replan_count: int = 0

        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            super().__init__(*args, **kwargs)

        async def replan(self, magentic_context: MagenticContext) -> Message:  # type: ignore[override]
            self.replan_count += 1
            return await super().replan(magentic_context)

    manager = CountingManager()
    wf = MagenticBuilder(
        participants=[DummyExec(name=manager.next_speaker_name)],
        enable_plan_review=True,
        manager=manager,
    ).build()

    # Wait for the initial plan review request
    req_event: WorkflowEvent | None = None
    async for ev in wf.run("do work", stream=True):
        if ev.type == "request_info" and ev.request_type is MagenticPlanReviewRequest:
            req_event = ev
    assert req_event is not None
    assert isinstance(req_event.data, MagenticPlanReviewRequest)

    # Send a revise response
    saw_second_review = False
    completed = False
    async for ev in wf.run(
        stream=True, responses={req_event.request_id: req_event.data.revise("Looks good; consider Z")}
    ):
        if ev.type == "request_info" and ev.request_type is MagenticPlanReviewRequest:
            saw_second_review = True
            req_event = ev

    # Approve the second review
    async for ev in wf.run(
        stream=True,
        responses={req_event.request_id: req_event.data.approve()},  # type: ignore[union-attr]
    ):
        if ev.type == "status" and ev.state == WorkflowRunState.IDLE:
            completed = True
            break

    assert completed
    assert manager.replan_count >= 1
    assert saw_second_review is True
    # Replan from FakeManager updates facts/plan to include A2 / Do Z
    assert manager.task_ledger is not None
    combined_text = (manager.task_ledger.facts.text or "") + (manager.task_ledger.plan.text or "")
    assert ("A2" in combined_text) or ("Do Z" in combined_text)


async def test_magentic_orchestrator_round_limit_produces_partial_result():
    manager = FakeManager(max_round_count=1)
    wf = MagenticBuilder(participants=[DummyExec(name=manager.next_speaker_name)], manager=manager).build()

    events: list[WorkflowEvent] = []
    async for ev in wf.run("round limit test", stream=True):
        events.append(ev)

    idle_status = next(
        (e for e in events if e.type == "status" and e.state == WorkflowRunState.IDLE),
        None,
    )
    assert idle_status is not None
    # Check that we got workflow output via WorkflowEvent with type "output"
    output_event = next((e for e in events if e.type == "output"), None)
    assert output_event is not None
    data = output_event.data
    assert isinstance(data, list)
    assert len(data) > 0  # type: ignore
    assert data[-1].role == "assistant"  # type: ignore
    assert all(isinstance(msg, Message) for msg in data)  # type: ignore


async def test_magentic_checkpoint_resume_round_trip():
    storage = InMemoryCheckpointStorage()

    manager1 = FakeManager()
    wf = MagenticBuilder(
        participants=[DummyExec(name=manager1.next_speaker_name)],
        enable_plan_review=True,
        checkpoint_storage=storage,
        manager=manager1,
    ).build()

    task_text = "checkpoint task"
    req_event: WorkflowEvent | None = None
    async for ev in wf.run(task_text, stream=True):
        if ev.type == "request_info" and ev.request_type is MagenticPlanReviewRequest:
            req_event = ev
    assert req_event is not None
    assert isinstance(req_event.data, MagenticPlanReviewRequest)

    checkpoints = await storage.list_checkpoints(workflow_name=wf.name)
    assert checkpoints
    checkpoints.sort(key=lambda cp: cp.timestamp)
    resume_checkpoint = checkpoints[-1]
    loaded_checkpoint = await storage.load(resume_checkpoint.checkpoint_id)
    assert loaded_checkpoint is not None
    # Regression check: checkpoints with pending request_info must include executor state.
    assert "_executor_state" in loaded_checkpoint.state
    assert "magentic_orchestrator" in loaded_checkpoint.state["_executor_state"]

    manager2 = FakeManager()
    wf_resume = MagenticBuilder(
        participants=[DummyExec(name=manager2.next_speaker_name)],
        enable_plan_review=True,
        checkpoint_storage=storage,
        manager=manager2,
    ).build()

    completed: WorkflowEvent | None = None
    req_event = None
    async for event in wf_resume.run(
        checkpoint_id=resume_checkpoint.checkpoint_id,
        stream=True,
    ):
        if event.type == "request_info" and event.request_type is MagenticPlanReviewRequest:
            req_event = event
    assert req_event is not None
    assert isinstance(req_event.data, MagenticPlanReviewRequest)

    responses = {req_event.request_id: req_event.data.approve()}
    async for event in wf_resume.run(stream=True, responses=responses):
        if event.type == "output":
            completed = event
    assert completed is not None

    orchestrator = next(exec for exec in wf_resume.executors.values() if isinstance(exec, MagenticOrchestrator))
    assert orchestrator._magentic_context is not None  # type: ignore[reportPrivateUsage]
    assert orchestrator._magentic_context.chat_history  # type: ignore[reportPrivateUsage]
    assert orchestrator._task_ledger is not None  # type: ignore[reportPrivateUsage]
    assert manager2.task_ledger is not None
    # Latest entry in chat history should be the task ledger plan
    assert orchestrator._magentic_context.chat_history[-1].text == orchestrator._task_ledger.text  # type: ignore[reportPrivateUsage]


class StubManagerAgent(BaseAgent):
    """Stub agent for testing StandardMagenticManager."""

    def run(
        self,
        messages: str | Content | Message | Sequence[str | Content | Message] | None = None,
        *,
        stream: bool = False,
        session: Any = None,
        **kwargs: Any,
    ) -> Awaitable[AgentResponse] | AsyncIterable[AgentResponseUpdate]:
        if stream:
            return self._run_stream()

        async def _run() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", ["ok"])])

        return _run()

    async def _run_stream(self) -> AsyncIterable[AgentResponseUpdate]:
        yield AgentResponseUpdate(message_deltas=[Message("assistant", ["ok"])])


async def test_standard_manager_plan_and_replan_via_complete_monkeypatch():
    mgr = StandardMagenticManager(StubManagerAgent())

    async def fake_complete_plan(messages: list[Message], **kwargs: Any) -> Message:
        # Return a different response depending on call order length
        if any("FACTS" in (m.text or "") for m in messages):
            return Message("assistant", ["- step A\n- step B"])
        return Message("assistant", ["GIVEN OR VERIFIED FACTS\n- fact1"])

    # First, patch to produce facts then plan
    mgr._complete = fake_complete_plan  # type: ignore[attr-defined]

    ctx = MagenticContext(task="T", participant_descriptions={"A": "desc"})
    combined = await mgr.plan(ctx.clone())
    # Assert structural headings and that steps appear in the combined ledger output.
    assert "We are working to address the following user request:" in combined.text
    assert "Here is the plan to follow as best as possible:" in combined.text
    assert any(t in combined.text for t in ("- step A", "- step B", "- step"))

    # Now replan with new outputs
    async def fake_complete_replan(messages: list[Message], **kwargs: Any) -> Message:
        if any("Please briefly explain" in (m.text or "") for m in messages):
            return Message("assistant", ["- new step"])
        return Message("assistant", ["GIVEN OR VERIFIED FACTS\n- updated"])

    mgr._complete = fake_complete_replan  # type: ignore[attr-defined]
    combined2 = await mgr.replan(ctx.clone())
    assert "updated" in combined2.text or "new step" in combined2.text


async def test_standard_manager_progress_ledger_success_and_error():
    mgr = StandardMagenticManager(agent=StubManagerAgent())
    ctx = MagenticContext(task="task", participant_descriptions={"alice": "desc"})

    # Success path: valid JSON
    async def fake_complete_ok(messages: list[Message], **kwargs: Any) -> Message:
        json_text = (
            '{"is_request_satisfied": {"reason": "r", "answer": false}, '
            '"is_in_loop": {"reason": "r", "answer": false}, '
            '"is_progress_being_made": {"reason": "r", "answer": true}, '
            '"next_speaker": {"reason": "r", "answer": "alice"}, '
            '"instruction_or_question": {"reason": "r", "answer": "do"}}'
        )
        return Message("assistant", [json_text])

    mgr._complete = fake_complete_ok  # type: ignore[attr-defined]
    ledger = await mgr.create_progress_ledger(ctx.clone())
    assert ledger.next_speaker.answer == "alice"

    # Error path: invalid JSON now raises to avoid emitting planner-oriented instructions to agents
    async def fake_complete_bad(messages: list[Message], **kwargs: Any) -> Message:
        return Message("assistant", ["not-json"])

    mgr._complete = fake_complete_bad  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError):
        await mgr.create_progress_ledger(ctx.clone())


class InvokeOnceManager(MagenticManagerBase):
    def __init__(self) -> None:
        super().__init__(max_round_count=5, max_stall_count=3, max_reset_count=2)
        self._invoked = False

    async def plan(self, magentic_context: MagenticContext) -> Message:
        return Message("assistant", ["ledger"])

    async def replan(self, magentic_context: MagenticContext) -> Message:
        return Message("assistant", ["re-ledger"])

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

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> Message:
        return Message("assistant", ["final"])


class StubThreadAgent(BaseAgent):
    def __init__(self, name: str | None = None) -> None:
        super().__init__(name=name or "agentA")

    def run(self, messages=None, *, stream: bool = False, session=None, **kwargs):  # type: ignore[override]
        if stream:
            return self._run_stream()

        async def _run():
            return AgentResponse(messages=[Message("assistant", ["thread-ok"], author_name=self.name)])

        return _run()

    async def _run_stream(self):
        yield AgentResponseUpdate(
            contents=[Content.from_text(text="thread-ok")],
            author_name=self.name,
            role="assistant",
        )


class StubAssistantsClient:
    pass  # class name used for branch detection


class StubAssistantsAgent(BaseAgent):
    client: object | None = None  # allow assignment via Pydantic field

    def __init__(self) -> None:
        super().__init__(name="agentA")
        self.client = StubAssistantsClient()  # type name contains 'AssistantsClient'

    def run(self, messages=None, *, stream: bool = False, session=None, **kwargs):  # type: ignore[override]
        if stream:
            return self._run_stream()

        async def _run():
            return AgentResponse(messages=[Message("assistant", ["assistants-ok"], author_name=self.name)])

        return _run()

    async def _run_stream(self):
        yield AgentResponseUpdate(
            contents=[Content.from_text(text="assistants-ok")],
            author_name=self.name,
            role="assistant",
        )


async def _collect_agent_responses_setup(participant: SupportsAgentRun) -> list[Message]:
    captured: list[Message] = []

    wf = MagenticBuilder(participants=[participant], intermediate_outputs=True, manager=InvokeOnceManager()).build()

    # Run a bounded stream to allow one invoke and then completion
    events: list[WorkflowEvent] = []
    async for ev in wf.run("task", stream=True):  # plan review disabled
        events.append(ev)
        # Capture streaming updates (type="output" with AgentResponseUpdate data)
        if ev.type == "output" and isinstance(ev.data, AgentResponseUpdate):
            captured.append(
                Message(
                    role=ev.data.role or "assistant",
                    text=ev.data.text or "",
                    author_name=ev.data.author_name,
                )
            )
        # Break on final AgentResponse output
        elif ev.type == "output" and isinstance(ev.data, AgentResponse):
            break

    return captured


async def test_agent_executor_invoke_with_thread_chat_client():
    agent = StubThreadAgent()
    captured = await _collect_agent_responses_setup(agent)
    assert any((m.author_name == agent.name and "ok" in (m.text or "")) for m in captured)


async def test_agent_executor_invoke_with_assistants_client_messages():
    agent = StubAssistantsAgent()
    captured = await _collect_agent_responses_setup(agent)
    assert any((m.author_name == agent.name and "ok" in (m.text or "")) for m in captured)


async def _collect_checkpoints(
    storage: InMemoryCheckpointStorage,
    workflow_name: str,
) -> list[WorkflowCheckpoint]:
    checkpoints = await storage.list_checkpoints(workflow_name=workflow_name)
    assert checkpoints
    checkpoints.sort(key=lambda cp: cp.timestamp)
    return checkpoints


async def test_magentic_checkpoint_resume_inner_loop_superstep():
    storage = InMemoryCheckpointStorage()

    workflow = MagenticBuilder(
        participants=[StubThreadAgent()], checkpoint_storage=storage, manager=InvokeOnceManager()
    ).build()

    async for _ in workflow.run("inner-loop task", stream=True):
        continue

    checkpoints = await _collect_checkpoints(storage, workflow.name)
    # The first checkpoint is after the manager has run.
    # The second checkpoint is after the participant has run.
    inner_loop_checkpoint = checkpoints[1]

    resumed = MagenticBuilder(
        participants=[StubThreadAgent()], checkpoint_storage=storage, manager=InvokeOnceManager()
    ).build()

    completed: WorkflowEvent | None = None
    async for event in resumed.run(checkpoint_id=inner_loop_checkpoint.checkpoint_id, stream=True):  # type: ignore[reportUnknownMemberType]
        if event.type == "output":
            completed = event

    assert completed is not None


async def test_magentic_checkpoint_resume_from_saved_state():
    """Test that we can resume workflow execution from a saved checkpoint."""
    storage = InMemoryCheckpointStorage()

    # Use the working InvokeOnceManager first to get a completed workflow
    manager = InvokeOnceManager()

    workflow = MagenticBuilder(participants=[StubThreadAgent()], checkpoint_storage=storage, manager=manager).build()

    async for event in workflow.run("checkpoint resume task", stream=True):
        if event.type == "output":
            break

    checkpoints = await _collect_checkpoints(storage, workflow.name)

    # Verify we can resume from the last saved checkpoint
    resumed_state = checkpoints[-1]  # Use the last checkpoint

    resumed_workflow = MagenticBuilder(
        participants=[StubThreadAgent()], checkpoint_storage=storage, manager=InvokeOnceManager()
    ).build()

    completed: WorkflowEvent | None = None
    async for event in resumed_workflow.run(checkpoint_id=resumed_state.checkpoint_id, stream=True):
        if event.type == "output":
            completed = event

    assert completed is not None


async def test_magentic_checkpoint_resume_rejects_participant_renames():
    storage = InMemoryCheckpointStorage()

    manager = InvokeOnceManager()

    workflow = MagenticBuilder(
        participants=[StubThreadAgent()],
        enable_plan_review=True,
        checkpoint_storage=storage,
        manager=manager,
    ).build()

    req_event: WorkflowEvent | None = None
    async for event in workflow.run("task", stream=True):
        if event.type == "request_info" and event.request_type is MagenticPlanReviewRequest:
            req_event = event

    assert req_event is not None
    assert isinstance(req_event.data, MagenticPlanReviewRequest)

    checkpoints = await _collect_checkpoints(storage, workflow.name)
    target_checkpoint = checkpoints[-1]

    renamed_workflow = MagenticBuilder(
        participants=[StubThreadAgent(name="renamedAgent")],
        enable_plan_review=True,
        checkpoint_storage=storage,
        manager=InvokeOnceManager(),
    ).build()

    with pytest.raises(WorkflowCheckpointException, match="Workflow graph has changed"):
        async for _ in renamed_workflow.run(
            stream=True,
            checkpoint_id=target_checkpoint.checkpoint_id,  # type: ignore[reportUnknownMemberType]
        ):
            pass


class NotProgressingManager(MagenticManagerBase):
    """
    A manager that never marks progress being made, to test stall/reset limits.
    """

    async def plan(self, magentic_context: MagenticContext) -> Message:
        return Message("assistant", ["ledger"])

    async def replan(self, magentic_context: MagenticContext) -> Message:
        return Message("assistant", ["re-ledger"])

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
        return MagenticProgressLedger(
            is_request_satisfied=MagenticProgressLedgerItem(reason="r", answer=False),
            is_in_loop=MagenticProgressLedgerItem(reason="r", answer=True),
            is_progress_being_made=MagenticProgressLedgerItem(reason="r", answer=False),
            next_speaker=MagenticProgressLedgerItem(reason="r", answer="agentA"),
            instruction_or_question=MagenticProgressLedgerItem(reason="r", answer="done"),
        )

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> Message:
        return Message("assistant", ["final"])


async def test_magentic_stall_and_reset_reach_limits():
    manager = NotProgressingManager(max_round_count=10, max_stall_count=0, max_reset_count=1)

    wf = MagenticBuilder(participants=[DummyExec("agentA")], manager=manager).build()

    events: list[WorkflowEvent] = []
    async for ev in wf.run("test limits", stream=True):
        events.append(ev)

    idle_status = next(
        (e for e in events if e.type == "status" and e.state == WorkflowRunState.IDLE),
        None,
    )
    assert idle_status is not None
    output_event = next((e for e in events if e.type == "output"), None)
    assert output_event is not None
    assert isinstance(output_event.data, list)
    assert all(isinstance(msg, Message) for msg in output_event.data)  # type: ignore
    assert len(output_event.data) > 0  # type: ignore
    assert output_event.data[-1].text is not None  # type: ignore
    assert output_event.data[-1].text == "Workflow terminated due to reaching maximum reset count."  # type: ignore


async def test_magentic_checkpoint_runtime_only() -> None:
    """Test checkpointing configured ONLY at runtime, not at build time."""
    storage = InMemoryCheckpointStorage()

    manager = FakeManager(max_round_count=10)
    wf = MagenticBuilder(participants=[DummyExec("agentA")], manager=manager).build()

    baseline_output: Message | None = None
    async for ev in wf.run("runtime checkpoint test", checkpoint_storage=storage, stream=True):
        if ev.type == "output":
            baseline_output = ev.data  # type: ignore[assignment]
        if ev.type == "status" and ev.state in (
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        ):
            break

    assert baseline_output is not None

    checkpoints = await storage.list_checkpoints(workflow_name=wf.name)
    assert len(checkpoints) > 0, "Runtime-only checkpointing should have created checkpoints"


async def test_magentic_checkpoint_runtime_overrides_buildtime() -> None:
    """Test that runtime checkpoint storage overrides build-time configuration."""
    import tempfile

    with (
        tempfile.TemporaryDirectory() as temp_dir1,
        tempfile.TemporaryDirectory() as temp_dir2,
    ):
        from agent_framework._workflows._checkpoint import FileCheckpointStorage

        buildtime_storage = FileCheckpointStorage(temp_dir1)
        runtime_storage = FileCheckpointStorage(temp_dir2)

        manager = FakeManager(max_round_count=10)
        wf = MagenticBuilder(
            participants=[DummyExec("agentA")], checkpoint_storage=buildtime_storage, manager=manager
        ).build()

        baseline_output: Message | None = None
        async for ev in wf.run("override test", checkpoint_storage=runtime_storage, stream=True):
            if ev.type == "output":
                baseline_output = ev.data  # type: ignore[assignment]
            if ev.type == "status" and ev.state in (
                WorkflowRunState.IDLE,
                WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
            ):
                break

        assert baseline_output is not None

        buildtime_checkpoints = await buildtime_storage.list_checkpoints(workflow_name=wf.name)
        runtime_checkpoints = await runtime_storage.list_checkpoints(workflow_name=wf.name)

        assert len(runtime_checkpoints) > 0, "Runtime storage should have checkpoints"
        assert len(buildtime_checkpoints) == 0, "Build-time storage should have no checkpoints when overridden"


# region Message Deduplication Tests


async def test_magentic_context_no_duplicate_on_reset():
    """Test that MagenticContext.reset() clears chat_history without leaving duplicates."""
    ctx = MagenticContext(task="task", participant_descriptions={"Alice": "Researcher"})

    # Add some history
    ctx.chat_history.append(Message("assistant", ["response1"]))
    ctx.chat_history.append(Message("assistant", ["response2"]))
    assert len(ctx.chat_history) == 2

    # Reset
    ctx.reset()

    # Verify clean slate
    assert len(ctx.chat_history) == 0, "chat_history should be empty after reset"

    # Add new history
    ctx.chat_history.append(Message("assistant", ["new_response"]))
    assert len(ctx.chat_history) == 1, "Should have exactly 1 message after adding to reset context"


async def test_magentic_checkpoint_restore_no_duplicate_history():
    """Test that checkpoint restore does not create duplicate messages in chat_history."""
    manager = FakeManager(max_round_count=10)
    storage = InMemoryCheckpointStorage()

    wf = MagenticBuilder(participants=[DummyExec("agentA")], checkpoint_storage=storage, manager=manager).build()

    # Run with conversation history to create initial checkpoint
    conversation: list[Message] = [
        Message("user", ["task_msg"]),
    ]

    async for event in wf.run(conversation, stream=True):
        if event.type == "status" and event.state in (
            WorkflowRunState.IDLE,
            WorkflowRunState.IDLE_WITH_PENDING_REQUESTS,
        ):
            break

    # Get checkpoint
    checkpoints = await storage.list_checkpoints(workflow_name=wf.name)
    assert len(checkpoints) > 0, "Should have created checkpoints"

    latest_checkpoint = checkpoints[-1]

    # Load checkpoint and verify no duplicates in state
    checkpoint_data = await storage.load(latest_checkpoint.checkpoint_id)
    assert checkpoint_data is not None

    # Check the magentic_context in the checkpoint
    for _, executor_state in checkpoint_data.metadata.items():
        if isinstance(executor_state, dict) and "magentic_context" in executor_state:
            ctx_data: dict[str, Any] = executor_state["magentic_context"]  # type: ignore
            chat_history = ctx_data.get("chat_history", [])  # type: ignore

            # Count unique messages by text
            texts = [  # type: ignore
                msg.get("text") or (msg.get("contents", [{}])[0].get("text") if msg.get("contents") else None)  # type: ignore
                for msg in chat_history  # type: ignore
            ]
            text_counts: dict[str, int] = {}
            for text in texts:  # type: ignore
                if text:
                    text_counts[text] = text_counts.get(text, 0) + 1  # type: ignore

            # Input messages should not be duplicated
            assert text_counts.get("history_msg", 0) <= 1, (
                f"'history_msg' appears {text_counts.get('history_msg', 0)} times in checkpoint - expected <= 1"
            )
            assert text_counts.get("task_msg", 0) <= 1, (
                f"'task_msg' appears {text_counts.get('task_msg', 0)} times in checkpoint - expected <= 1"
            )


# endregion

# region Manager Factory Tests


def test_magentic_builder_rejects_multiple_manager_configurations():
    """Test that configuring multiple managers raises ValueError."""
    manager = FakeManager()
    agent = StubAgent("agentA", "reply")

    with pytest.raises(ValueError, match=r"Exactly one of"):
        MagenticBuilder(participants=[agent], manager=manager, manager_agent=StubManagerAgent())


def test_magentic_builder_requires_exactly_one_manager_option():
    """Test that exactly one manager option must be provided."""
    manager = FakeManager()
    agent = StubAgent("agentA", "reply")

    def manager_factory() -> MagenticManagerBase:
        return FakeManager()

    # No options provided - only fails at build() time
    with pytest.raises(ValueError, match="No manager configured"):
        MagenticBuilder(participants=[agent]).build()

    # Multiple options provided
    with pytest.raises(ValueError, match="Exactly one of"):
        MagenticBuilder(participants=[agent], manager=manager, manager_factory=manager_factory)


async def test_magentic_with_manager_factory():
    """Test workflow creation using manager_factory."""
    factory_call_count = 0

    def manager_factory() -> MagenticManagerBase:
        nonlocal factory_call_count
        factory_call_count += 1
        return FakeManager()

    agent = StubAgent("agentA", "reply from agentA")
    workflow = MagenticBuilder(participants=[agent], manager_factory=manager_factory).build()

    # Factory should be called during build
    assert factory_call_count == 1

    outputs: list[WorkflowEvent] = []
    async for event in workflow.run("test task", stream=True):
        if event.type == "output":
            outputs.append(event)

    assert len(outputs) == 1


async def test_magentic_with_agent_factory():
    """Test workflow creation using agent_factory for StandardMagenticManager."""
    factory_call_count = 0

    def agent_factory() -> SupportsAgentRun:
        nonlocal factory_call_count
        factory_call_count += 1
        return cast(SupportsAgentRun, StubManagerAgent())

    participant = StubAgent("agentA", "reply from agentA")
    workflow = MagenticBuilder(
        participants=[participant], manager_agent_factory=agent_factory, max_round_count=1
    ).build()

    # Factory should be called during build
    assert factory_call_count == 1

    # Verify workflow can be started (may not complete successfully due to stub behavior)
    event_count = 0
    async for _ in workflow.run("test task", stream=True):
        event_count += 1
        if event_count > 10:
            break

    assert event_count > 0


async def test_magentic_manager_factory_reusable_builder():
    """Test that the builder can be reused to build multiple workflows with manager factory."""
    factory_call_count = 0

    def manager_factory() -> MagenticManagerBase:
        nonlocal factory_call_count
        factory_call_count += 1
        return FakeManager()

    agent = StubAgent("agentA", "reply from agentA")
    builder = MagenticBuilder(participants=[agent], manager_factory=manager_factory)

    # Build first workflow
    wf1 = builder.build()
    assert factory_call_count == 1

    # Build second workflow
    wf2 = builder.build()
    assert factory_call_count == 2

    # Verify that the two workflows have different orchestrator instances
    orchestrator1 = next(e for e in wf1.executors.values() if isinstance(e, MagenticOrchestrator))
    orchestrator2 = next(e for e in wf2.executors.values() if isinstance(e, MagenticOrchestrator))
    assert orchestrator1 is not orchestrator2


def test_magentic_agent_factory_with_standard_manager_options():
    """Test that agent_factory properly passes through standard manager options."""
    factory_call_count = 0

    def agent_factory() -> SupportsAgentRun:
        nonlocal factory_call_count
        factory_call_count += 1
        return cast(SupportsAgentRun, StubManagerAgent())

    # Custom options to verify they are passed through
    custom_max_stall_count = 5
    custom_max_reset_count = 2
    custom_max_round_count = 10
    custom_facts_prompt = "Custom facts prompt: {task}"
    custom_plan_prompt = "Custom plan prompt: {team}"
    custom_full_prompt = "Custom full prompt: {task} {team} {facts} {plan}"
    custom_facts_update_prompt = "Custom facts update: {task} {old_facts}"
    custom_plan_update_prompt = "Custom plan update: {team}"
    custom_progress_prompt = "Custom progress: {task} {team} {names}"
    custom_final_prompt = "Custom final: {task}"

    # Create a custom task ledger
    from agent_framework_orchestrations._magentic import _MagenticTaskLedger  # type: ignore

    custom_task_ledger = _MagenticTaskLedger(
        facts=Message("assistant", ["Custom facts"]),
        plan=Message("assistant", ["Custom plan"]),
    )

    participant = StubAgent("agentA", "reply from agentA")
    workflow = MagenticBuilder(
        participants=[participant],
        manager_agent_factory=agent_factory,
        task_ledger=custom_task_ledger,
        max_stall_count=custom_max_stall_count,
        max_reset_count=custom_max_reset_count,
        max_round_count=custom_max_round_count,
        task_ledger_facts_prompt=custom_facts_prompt,
        task_ledger_plan_prompt=custom_plan_prompt,
        task_ledger_full_prompt=custom_full_prompt,
        task_ledger_facts_update_prompt=custom_facts_update_prompt,
        task_ledger_plan_update_prompt=custom_plan_update_prompt,
        progress_ledger_prompt=custom_progress_prompt,
        final_answer_prompt=custom_final_prompt,
    ).build()

    # Factory should be called during build
    assert factory_call_count == 1

    # Get the orchestrator and verify the manager has the custom options
    orchestrator = next(e for e in workflow.executors.values() if isinstance(e, MagenticOrchestrator))
    manager = orchestrator._manager  # type: ignore[reportPrivateUsage]

    # Verify the manager is a StandardMagenticManager with the expected options
    from agent_framework.orchestrations import StandardMagenticManager

    assert isinstance(manager, StandardMagenticManager)
    assert manager.task_ledger is custom_task_ledger
    assert manager.max_stall_count == custom_max_stall_count
    assert manager.max_reset_count == custom_max_reset_count
    assert manager.max_round_count == custom_max_round_count
    assert manager.task_ledger_facts_prompt == custom_facts_prompt
    assert manager.task_ledger_plan_prompt == custom_plan_prompt
    assert manager.task_ledger_full_prompt == custom_full_prompt
    assert manager.task_ledger_facts_update_prompt == custom_facts_update_prompt
    assert manager.task_ledger_plan_update_prompt == custom_plan_update_prompt
    assert manager.progress_ledger_prompt == custom_progress_prompt
    assert manager.final_answer_prompt == custom_final_prompt


# endregion
