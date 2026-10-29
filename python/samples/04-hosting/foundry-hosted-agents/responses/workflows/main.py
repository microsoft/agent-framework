# /// script
# dependencies = ["agent-framework-foundry-hosting", "agent-framework-foundry", "azure-identity", "python-dotenv"]
# ///
# Copyright (c) Microsoft. All rights reserved.

"""Host a native slogan workflow with typed application input and fresh request-owned agents."""

import os

from agent_framework import (
    Agent,
    AgentExecutor,
    AgentExecutorRequest,
    Executor,
    Message,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import (
    CheckpointStoreProvider,
    HostedResponseRequest,
    ResponsesHostServer,
    WorkflowTurn,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class SloganRequest(BaseModel):
    topic: str = Field(min_length=1)
    style: str = Field(default="retro", min_length=1)


class SloganAgent(Agent):
    """Own the credential and project client created specifically for this sample's agent."""

    def __init__(self, name: str, instructions: str) -> None:
        endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
        model = os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
        self.credential = DefaultAzureCredential()
        try:
            client = FoundryChatClient(project_endpoint=endpoint, model=model, credential=self.credential)
        except BaseException:
            self.credential.close()
            raise
        self.project_client = client.project_client
        super().__init__(client=client, name=name, instructions=instructions, default_options={"store": False})

    async def close(self) -> None:
        try:
            await super().close()
        finally:
            await self.project_client.close()
            self.credential.close()


class StartExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="start")

    @handler
    async def start(self, request: SloganRequest, ctx: WorkflowContext[AgentExecutorRequest, str]) -> None:
        ctx.set_state("slogan_style", request.style)
        await ctx.send_message(
            AgentExecutorRequest(
                messages=[
                    Message("user", f"Create a {request.style} slogan for {request.topic}."),
                ]
            )
        )


def build_workflow(request: HostedResponseRequest) -> Workflow:
    """Build fresh graphs, executors, agents, clients, and credentials with stable graph IDs."""
    start = StartExecutor()
    writer = AgentExecutor(
        SloganAgent("writer", "Write one short slogan for the supplied topic and style."),
        id="writer",
        context_mode="last_agent",
    )
    legal = AgentExecutor(
        SloganAgent("legal", "Review the slogan and remove misleading claims."), id="legal", context_mode="last_agent"
    )
    formatter = AgentExecutor(
        SloganAgent("formatter", "Format the final slogan in a playful retro style."),
        id="formatter",
        context_mode="last_agent",
    )
    return (
        WorkflowBuilder(name="slogan-workflow-v1", start_executor=start, output_from=[formatter])
        .add_edge(start, writer)
        .add_edge(writer, legal)
        .add_edge(legal, formatter)
        .build()
    )


async def parse_response(request: HostedResponseRequest) -> WorkflowTurn[SloganRequest]:
    """Parse only this turn's Responses text; history and checkpoint selection belong to the host."""
    return WorkflowTurn(input=SloganRequest.model_validate_json(await request.get_input_text() or ""))


def main() -> None:
    load_dotenv()
    ResponsesHostServer(
        workflow=build_workflow,
        parse_response=parse_response,
        checkpoint_store_provider=CheckpointStoreProvider(
            allowed_checkpoint_types=[f"{SloganRequest.__module__}:{SloganRequest.__qualname__}"],
        ),
    ).run()


if __name__ == "__main__":
    main()
