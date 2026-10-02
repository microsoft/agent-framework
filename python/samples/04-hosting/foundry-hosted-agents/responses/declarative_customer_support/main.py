# /// script
# dependencies = [
#   "agent-framework-declarative",
#   "agent-framework-foundry-hosting",
#   "agent-framework-foundry",
#   "agent-framework-openai",
#   "azure-identity",
#   "python-dotenv",
# ]
# ///
# Copyright (c) Microsoft. All rights reserved.

"""Host a native, checkpointed declarative customer-support workflow.

The Power Fx actions in workflow.yaml require the .NET runtime included by
this sample's Dockerfile. Do not use a ZIP/code-only deployment for it.
"""

import os
from pathlib import Path
from typing import Any, Literal

from agent_framework import Agent, Message, Workflow
from agent_framework.foundry import FoundryChatClient
from agent_framework_declarative import WorkflowFactory
from agent_framework_foundry_hosting import (
    HostedResponseRequest,
    ResponsesHostServer,
    WorkflowTurn,
    response_input_messages,
)
from agent_framework_openai import OpenAIChatOptions
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class TriageResponse(BaseModel):
    Category: Literal["Technical", "Billing", "General"] = Field(
        description="Route the user's request to technical, billing, or general support.",
    )
    NeedsClarification: bool = Field(description="Whether one focused follow-up question is required.")
    ClarificationQuestion: str = ""
    Reply: str = ""


class SupportAgent(Agent):
    """Own all resources created for one declarative workflow instance."""

    def __init__(
        self,
        name: str,
        instructions: str,
        *,
        default_options: OpenAIChatOptions[Any] | None = None,
    ) -> None:
        self.credential = DefaultAzureCredential()
        try:
            client = FoundryChatClient(
                project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                credential=self.credential,
            )
        except BaseException:
            self.credential.close()
            raise
        self.project_client = client.project_client
        super().__init__(
            client=client,
            name=name,
            instructions=instructions,
            default_options=default_options or OpenAIChatOptions(store=False),
        )

    async def close(self) -> None:
        try:
            await super().close()
        finally:
            await self.project_client.close()
            self.credential.close()


def build_workflow(request: HostedResponseRequest) -> Workflow:
    """Load a fresh declarative graph with fresh request-owned agents and stable YAML IDs."""
    triage = SupportAgent(
        "TriageAgent",
        "Classify the conversation, ask one focused clarification when needed, or answer a general question.",
        default_options=OpenAIChatOptions[Any](response_format=TriageResponse, store=False),
    )
    technical = SupportAgent(
        "TechSupportAgent",
        "Give one concrete troubleshooting step at a time using the conversation history.",
    )
    billing = SupportAgent(
        "BillingAgent",
        "Help with invoice, subscription, refund, and payment questions using the conversation history.",
    )
    factory = WorkflowFactory(
        agents={
            "TriageAgent": triage,
            "TechSupportAgent": technical,
            "BillingAgent": billing,
        }
    )
    return factory.create_workflow_from_yaml_path(str(Path(__file__).parent / "workflow.yaml"))


async def parse_response(request: HostedResponseRequest) -> WorkflowTurn[list[Message]]:
    """Use the explicit current-turn message migration helper; checkpoints retain prior workflow state."""
    return WorkflowTurn(input=await response_input_messages(request))


def main() -> None:
    load_dotenv()
    ResponsesHostServer(workflow=build_workflow, parse_response=parse_response).run()


if __name__ == "__main__":
    main()
