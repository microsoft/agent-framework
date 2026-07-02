# Copyright (c) Microsoft. All rights reserved.

import os
from pathlib import Path
from typing import Literal

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_declarative import WorkflowFactory
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables from .env file
load_dotenv()


# --- Structured triage response --------------------------------------------------

class TriageResponse(BaseModel):
    """Triage decision produced from the conversation so far."""

    Category: Literal["Technical", "Billing", "General"] = Field(
        description=(
            "The best category for the user's request. "
            "Use 'Technical' for hardware/software/network issues, "
            "'Billing' for invoices/subscriptions/refunds, and "
            "'General' for anything else (greetings, FAQs, small talk)."
        ),
    )
    NeedsClarification: bool = Field(
        description=(
            "True if you cannot confidently classify the request yet and "
            "need to ask the user one focused follow-up question."
        ),
    )
    ClarificationQuestion: str = Field(
        default="",
        description=(
            "A single, polite follow-up question to ask the user. "
            "Required when NeedsClarification is true; otherwise empty."
        ),
    )
    Reply: str = Field(
        default="",
        description=(
            "A natural-language reply to the user. "
            "Used when Category is 'General'; otherwise may be left empty."
        ),
    )


# --- Agent instructions ----------------------------------------------------------

TRIAGE_INSTRUCTIONS = """
You are the front-line triage agent for a customer support workflow.

You will see the full conversation so far. Decide whether to:
- Ask the user one focused follow-up question (set NeedsClarification = true), or
- Route the conversation to the right specialist by setting Category, or
- Answer directly for general/small-talk requests via Reply.

Be efficient: do not ask a clarification if a category is already clear.
""".strip()

TECH_SUPPORT_INSTRUCTIONS = """
You are a senior technical support specialist. The conversation history shows
what the user has told you so far and which steps were already attempted.

Provide one concrete next troubleshooting step at a time, then wait for the
user's response. Be concise and friendly. If the issue appears resolved,
congratulate the user and ask if there's anything else.
""".strip()

BILLING_INSTRUCTIONS = """
You are a customer billing specialist. The conversation history shows what
the user has asked.

Help the user with invoice, subscription, refund, and payment-method
questions. If you need account details (e.g., last 4 of card, account email),
ask for them one at a time. Keep responses short and polite.
""".strip()


# --- Host setup ------------------------------------------------------------------

def main() -> None:
    workflow_path = Path(__file__).parent / "workflow.yaml"

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    # The workflow's InvokeAzureAgent actions reference these agents by name.
    triage_agent = Agent(
        client=client,
        name="TriageAgent",
        instructions=TRIAGE_INSTRUCTIONS,
        default_options={"response_format": TriageResponse, "store": False},
    )
    tech_support_agent = Agent(
        client=client,
        name="TechSupportAgent",
        instructions=TECH_SUPPORT_INSTRUCTIONS,
        default_options={"store": False},
    )
    billing_agent = Agent(
        client=client,
        name="BillingAgent",
        instructions=BILLING_INSTRUCTIONS,
        default_options={"store": False},
    )

    factory = WorkflowFactory(
        agents={
            "TriageAgent": triage_agent,
            "TechSupportAgent": tech_support_agent,
            "BillingAgent": billing_agent,
        },
    )

    workflow = factory.create_workflow_from_yaml_path(str(workflow_path))

    # Wrap the declarative workflow as an AIAgent so it can be served behind
    # the Responses protocol. Each user turn re-runs the workflow with the
    # full conversation history available via Conversation.messages.
    workflow_agent = workflow.as_agent(
        name="declarative-customer-support",
        description=(
            "A multi-turn customer-support triage workflow that routes "
            "between technical and billing specialists based on the "
            "conversation history."
        ),
    )

    ResponsesHostServer(workflow_agent).run()


if __name__ == "__main__":
    main()
