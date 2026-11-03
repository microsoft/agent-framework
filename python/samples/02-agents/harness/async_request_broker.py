# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import sys
from collections.abc import Awaitable, Mapping, Sequence
from typing import Any

from agent_framework import (
    Agent,
    AgentSession,
    BaseChatClient,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    Message,
)
from agent_framework_tools.shell import LocalShellTool

"""MAF approval pause-and-resume for shell commands.

Agent Framework's approval contract is pause-and-resume, not "block and wait":

1. A tool created with ``approval_mode="always_require"`` does NOT run. The
   agent returns early and ``response.user_input_requests`` contains a
   function-approval request.
2. Your application delivers that request to whoever decides (a UI, a chat
   channel, a reviewer) over a transport that YOU own.
3. When a decision arrives, call ``agent.run(...)`` again with the SAME
   ``AgentSession`` and an approval response built with
   ``request.to_function_approval_response(approved)``.

The framework deliberately ships no request broker: where pending requests
live, how they reach a client, and how long they wait are application concerns.

This sample shows that split. ``_PendingApprovals`` below is a minimal
``asyncio.Future``-based mailbox that stands in for your transport. It is
process-lifetime only: if the process exits, pending requests are lost. It is
NOT a substitute for a durable queue or workflow engine; use one of those when
approvals must survive restarts or span multiple workers.

No LLM or credentials are needed. A scripted chat client emits a shell tool
call, and the real ``LocalShellTool`` runs it only after approval. Shell
policy/outcome events are emitted on the ``agent_framework.shell.audit``
logger; the sample enables it so you can see them.
"""


class _AuditPrinter(logging.Handler):
    """Print shell audit events (policy decision and outcome) with their structured fields."""

    _FIELDS = ("policy_decision", "outcome", "exit_code", "timed_out")

    def emit(self, record: logging.LogRecord) -> None:
        fields = {k: record.__dict__[k] for k in self._FIELDS if k in record.__dict__}
        print(f"    [audit] {record.getMessage()} {fields}")


_audit_logger = logging.getLogger("agent_framework.shell.audit")
_audit_logger.setLevel(logging.INFO)
_audit_logger.addHandler(_AuditPrinter())


class _PendingApprovals:
    """Application-owned mailbox: request id -> Future[bool]. Process-lifetime only."""

    def __init__(self) -> None:
        self._futures: dict[str, asyncio.Future[bool]] = {}

    def submit(self, request_id: str) -> asyncio.Future[bool]:
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._futures[request_id] = future
        return future

    def answer(self, request_id: str, approved: bool) -> None:
        future = self._futures.pop(request_id, None)
        if future is not None and not future.done():
            future.set_result(approved)

    def discard(self, request_id: str) -> None:
        self._futures.pop(request_id, None)

    @property
    def pending_count(self) -> int:
        return len(self._futures)


class _ScriptedShellClient(FunctionInvocationLayer, BaseChatClient):
    """Stands in for an LLM: asks to run one shell command, then summarizes."""

    def __init__(self, command: str) -> None:
        super().__init__()
        self._command = command
        self._asked = False

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any,
    ) -> Awaitable[ChatResponse]:
        async def _get() -> ChatResponse:
            if not self._asked:
                self._asked = True
                call = Content.from_function_call(
                    call_id="call-1", name="run_shell", arguments={"command": self._command}
                )
                return ChatResponse(messages=Message(role="assistant", contents=[call]))
            return ChatResponse(messages=Message(role="assistant", contents=["The command finished."]))

        return _get()


def _make_agent(command: str) -> Agent[Any]:
    shell = LocalShellTool(mode="stateless", approval_mode="always_require")
    return Agent(client=_ScriptedShellClient(command), tools=[shell.as_function()])


async def simulated_client(pending: _PendingApprovals, request_id: str, *, approve: bool, delay: float) -> None:
    """Simulate a remote reviewer answering after a delay (or never, if delay is None-like)."""
    await asyncio.sleep(delay)
    print(f"[client] {'Approving' if approve else 'Denying'} {request_id}")
    pending.answer(request_id, approve)


async def run_with_approval(
    agent: Agent[Any],
    session: AgentSession,
    pending: _PendingApprovals,
    prompt: str,
    *,
    answer_timeout: float,
    client_task_factory: Any,
) -> str:
    """Drive pause-and-resume. ``client_task_factory(request_id)`` starts the simulated client."""
    response = await agent.run(prompt, session=session)
    if not response.user_input_requests:
        return response.text

    request = response.user_input_requests[0]
    assert request.function_call is not None
    request_id = request.id or request.function_call.call_id
    print(f"[server] Paused: approval needed for {request.function_call.name}({request.function_call.arguments})")

    # Deliver the request to the client over *your* transport, then wait for a decision.
    decision = pending.submit(request_id)
    client_task = client_task_factory(request_id)
    try:
        approved = await asyncio.wait_for(decision, timeout=answer_timeout)
    except asyncio.TimeoutError:
        # Nobody answered. The agent is NOT blocked -- it already returned -- but this
        # conversation is stuck in a "pending approval" state until you act. Decide a
        # policy: keep waiting, escalate, or resume with a denial.
        print(f"[server] No answer within {answer_timeout}s; request {request_id} is still unresolved.")
        pending.discard(request_id)
        client_task.cancel()
        return "STUCK: approval was never answered (session left paused)"

    # Resume: same session, plus the approval response.
    print(f"[server] Resuming with approved={approved}")
    resumed = await agent.run(
        [
            Message("assistant", [request]),
            Message("user", [request.to_function_approval_response(approved)]),
        ],
        session=session,
    )
    return resumed.text


async def main() -> None:
    command = "Write-Output hello" if sys.platform == "win32" else "echo hello from approved shell"
    pending = _PendingApprovals()

    print("=== 1. Approved: the command runs after the client says yes ===")
    agent, session = _make_agent(command), AgentSession()
    print(
        "[agent]",
        await run_with_approval(
            agent,
            session,
            pending,
            "Run the greeting command",
            answer_timeout=2.0,
            client_task_factory=lambda rid: asyncio.create_task(
                simulated_client(pending, rid, approve=True, delay=0.1)
            ),
        ),
    )

    print("\n=== 2. Denied: the command never runs ===")
    agent, session = _make_agent(command), AgentSession()
    print(
        "[agent]",
        await run_with_approval(
            agent,
            session,
            pending,
            "Run the greeting command",
            answer_timeout=2.0,
            client_task_factory=lambda rid: asyncio.create_task(
                simulated_client(pending, rid, approve=False, delay=0.1)
            ),
        ),
    )

    print("\n=== 3. Nobody answers: the session is stuck pending ===")
    agent, session = _make_agent(command), AgentSession()
    print(
        "[agent]",
        await run_with_approval(
            agent,
            session,
            pending,
            "Run the greeting command",
            answer_timeout=0.3,
            client_task_factory=lambda rid: asyncio.create_task(
                simulated_client(pending, rid, approve=True, delay=30.0)
            ),
        ),
    )
    print(f"Pending requests: {pending.pending_count}")


if __name__ == "__main__":
    asyncio.run(main())
