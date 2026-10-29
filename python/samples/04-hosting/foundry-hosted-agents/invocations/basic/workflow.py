# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "agent-framework-foundry-hosting",
# ]
# ///
# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler, response_handler
from agent_framework_foundry_hosting import CheckpointStoreProvider, InvocationsHostServer, WorkflowTurn
from starlette.requests import Request

"""Host typed tickets and durable review replies as a native Invocations workflow.

This deterministic example needs no model or Azure credentials to run locally.
The host restores workflow state, not a shared Workflow or workflow.as_agent().
"""


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    question: str
    require_review: bool = True


@dataclass(frozen=True)
class TicketState:
    turn: int = 0
    last_ticket_id: str | None = None


@dataclass(frozen=True)
class TicketReview:
    ticket_id: str
    question: str
    turn: int


@dataclass(frozen=True)
class TicketDecision:
    approved: bool


@dataclass(frozen=True)
class TicketResult:
    ticket_id: str
    turn: int
    status: Literal["received", "approved", "rejected"]


# 1. Use a typed start executor and checkpoint-supported application state.
class TicketStart(Executor):
    def __init__(self) -> None:
        super().__init__(id="ticket_start")

    @handler
    async def run(self, ticket: Ticket, ctx: WorkflowContext[None, TicketResult]) -> None:
        state = ctx.get_state("tickets", TicketState())
        if not isinstance(state, TicketState):
            raise TypeError("The restored tickets state must be TicketState.")
        turn = state.turn + 1
        ctx.set_state("tickets", TicketState(turn=turn, last_ticket_id=ticket.ticket_id))
        if ticket.require_review:
            await ctx.request_info(
                TicketReview(ticket.ticket_id, ticket.question, turn),
                response_type=TicketDecision,
            )
        else:
            await ctx.yield_output(TicketResult(ticket.ticket_id, turn, "received"))

    @response_handler
    async def review(
        self,
        request: TicketReview,
        decision: TicketDecision,
        ctx: WorkflowContext[None, TicketResult],
    ) -> None:
        await ctx.yield_output(
            TicketResult(request.ticket_id, request.turn, "approved" if decision.approved else "rejected")
        )


# 2. Build fresh executors for each request, with stable graph and executor IDs.
def build_workflow(_request: Request) -> Workflow:
    return WorkflowBuilder(name="ticket-workflow", start_executor=TicketStart()).build()


# 3. The application owns JSON validation and typed input/reply conversion.
def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("Duplicate JSON fields are not allowed.")
        values[key] = value
    return values


async def parse_request(request: Request) -> WorkflowTurn[Ticket]:
    payload: Any = json.loads(await request.body(), object_pairs_hook=unique_json_object)
    if not isinstance(payload, dict):
        raise ValueError("The request must be a JSON object.")
    stream = payload.get("stream", False)
    if not isinstance(stream, bool):
        raise ValueError("stream must be a boolean.")

    if "responses" in payload:
        if set(payload) - {"responses", "stream"}:
            raise ValueError("A review reply accepts only responses and stream.")
        responses = payload["responses"]
        if not isinstance(responses, dict) or not responses:
            raise ValueError("responses must be a nonempty object keyed by pending request IDs.")
        decisions: dict[str, TicketDecision] = {}
        for request_id, response in responses.items():
            if not isinstance(request_id, str) or not request_id:
                raise ValueError("Each response needs a nonempty request ID.")
            if (
                not isinstance(response, dict)
                or set(response) != {"approved"}
                or not isinstance(response["approved"], bool)
            ):
                raise ValueError("Each response must contain exactly one boolean approved field.")
            decisions[request_id] = TicketDecision(approved=response["approved"])
        return WorkflowTurn(responses=decisions, stream=stream)

    if set(payload) - {"ticket_id", "question", "require_review", "stream"}:
        raise ValueError("A ticket accepts only ticket_id, question, require_review and stream.")
    ticket_id = payload.get("ticket_id")
    question = payload.get("question")
    require_review = payload.get("require_review", True)
    if not isinstance(ticket_id, str) or not ticket_id.strip() or not isinstance(question, str) or not question.strip():
        raise ValueError("ticket_id and question must be nonempty strings.")
    if not isinstance(require_review, bool):
        raise ValueError("require_review must be a boolean.")
    return WorkflowTurn(input=Ticket(ticket_id, question, require_review), stream=stream)


# 4. Allow only these application types when decoding durable checkpoints.
def main() -> None:
    checkpoints = CheckpointStoreProvider(
        allowed_checkpoint_types=[
            f"{__name__}:{value.__qualname__}"
            for value in (Ticket, TicketState, TicketReview, TicketDecision, TicketResult)
        ]
    )
    InvocationsHostServer(
        workflow=build_workflow,
        parse_request=parse_request,
        checkpoint_store_provider=checkpoints,
    ).run()


if __name__ == "__main__":
    main()

# A new ticket normally emits request_info with its typed TicketReview payload.
# Reply with {"responses": {"<request_id>": {"approved": true}}} in the same sandbox.
# require_review=false produces a typed TicketResult immediately.
# stream=true emits framed request_info/output, then done only after the cursor is saved.
