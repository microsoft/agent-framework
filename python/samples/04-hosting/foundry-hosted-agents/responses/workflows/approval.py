# /// script
# dependencies = ["agent-framework-foundry-hosting", "pydantic"]
# ///
# Copyright (c) Microsoft. All rights reserved.

"""Pause a native typed workflow for approval; simulate publication without external side effects."""

import uuid

from agent_framework import (
    Content,
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)
from agent_framework_foundry_hosting import (
    CheckpointStoreProvider,
    HostedResponseRequest,
    ResponsesHostServer,
    WorkflowTurn,
)
from pydantic import BaseModel, Field


class PublicationRequest(BaseModel):
    summary: str = Field(min_length=1)


class PublicationResult(BaseModel):
    summary: str
    approved: bool


class PublicationExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="publication")

    @handler
    async def review(self, request: PublicationRequest, ctx: WorkflowContext[str, PublicationResult]) -> None:
        ctx.set_state("summary", request.summary)
        request_id = uuid.uuid4().hex
        call = Content.from_function_call(
            uuid.uuid4().hex,
            "publish_summary",
            arguments={"summary": request.summary},
            id=request_id,
        )
        await ctx.request_info(Content.from_function_approval_request(request_id, call), Content)

    @response_handler
    async def decide(self, request: Content, response: Content, ctx: WorkflowContext[str, PublicationResult]) -> None:
        await ctx.yield_output(PublicationResult(summary=ctx.get_state("summary"), approved=response.approved is True))


def build_workflow(request: HostedResponseRequest) -> Workflow:
    return WorkflowBuilder(name="approved-publication-v1", start_executor=PublicationExecutor()).build()


async def parse_response(request: HostedResponseRequest) -> WorkflowTurn[PublicationRequest]:
    items = await request.get_input_items()
    if any(item.get("type") == "mcp_approval_response" for item in items):
        return WorkflowTurn(responses=await request.get_workflow_responses())
    return WorkflowTurn(input=PublicationRequest.model_validate_json(await request.get_input_text() or ""))


def main() -> None:
    ResponsesHostServer(
        workflow=build_workflow,
        parse_response=parse_response,
        checkpoint_store_provider=CheckpointStoreProvider(
            allowed_checkpoint_types=[f"{PublicationRequest.__module__}:{PublicationRequest.__qualname__}"],
        ),
    ).run()


if __name__ == "__main__":
    main()
