# Copyright (c) Microsoft. All rights reserved.

"""AG-UI handoff workflow demo backend.

This demo exposes a dynamic HandoffBuilder workflow through AG-UI.
It intentionally includes two interrupt styles:

1. Tool approval (`function_approval_request`) for `submit_refund` and `submit_replacement`
2. Follow-up human input (`HandoffAgentUserRequest`) when an agent needs user details

Run this server and pair it with the frontend in `../frontend`.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import random

import uvicorn
from agent_framework import (
    Agent,
    Message,
    Workflow,
    tool,
)
from agent_framework.ag_ui import AgentFrameworkWorkflow, add_agent_framework_fastapi_endpoint
from agent_framework.orchestrations import HandoffBuilder
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logger = logging.getLogger(__name__)


@tool(approval_mode="always_require")
def submit_refund(refund_description: str, amount: str, order_id: str) -> str:
    """Capture a refund request for manual review before processing."""
    return f"refund recorded for order {order_id} (amount: {amount}) with details: {refund_description}"


@tool(approval_mode="always_require")
def submit_replacement(order_id: str, shipping_preference: str, replacement_note: str) -> str:
    """Capture a replacement request for manual review before processing."""
    return (
        f"replacement recorded for order {order_id} (shipping: {shipping_preference}) with details: {replacement_note}"
    )


@tool(approval_mode="never_require")
def lookup_order_details(order_id: str) -> dict[str, str]:
    """Return synthetic order details for a given order ID."""
    normalized_order_id = "".join(ch for ch in order_id if ch.isdigit()) or order_id
    rng = random.Random(normalized_order_id)
    catalog = [
        "Wireless Headphones",
        "Mechanical Keyboard",
        "Gaming Mouse",
        "27-inch Monitor",
        "USB-C Dock",
        "Bluetooth Speaker",
        "Laptop Stand",
    ]
    item_name = catalog[rng.randrange(len(catalog))]
    amount = f"${rng.randint(39, 349)}.{rng.randint(0, 99):02d}"
    purchase_date = f"2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    return {
        "order_id": normalized_order_id,
        "item_name": item_name,
        "amount": amount,
        "currency": "USD",
        "purchase_date": purchase_date,
        "status": "delivered",
    }


def create_agents() -> tuple[Agent, Agent, Agent]:
    """Create triage, refund, and order agents for the handoff workflow."""

    from agent_framework.azure import AzureOpenAIResponsesClient
    from azure.identity import AzureCliCredential

    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    triage = Agent(
        id="triage_agent",
        name="triage_agent",
        instructions=(
            "You are the customer support triage agent.\n"
            "Routing policy:\n"
            "1. Route refund-related requests to refund_agent.\n"
            "2. Route replacement/shipping requests to order_agent.\n"
            "3. Do not force replacement if the user asked for refund only.\n"
            "4. If the issue is fully resolved, send a concise wrap-up that ends with exactly: Case complete."
        ),
        client=client,
    )

    refund = Agent(
        id="refund_agent",
        name="refund_agent",
        instructions=(
            "You are the refund specialist.\n"
            "Workflow policy:\n"
            "1. If order_id is missing, ask only for order_id.\n"
            "2. Once order_id is available, call lookup_order_details(order_id) to retrieve item and amount.\n"
            "3. Do not ask the customer how much they paid unless lookup_order_details fails.\n"
            "4. If user intent is ambiguous, ask one clear choice question and wait for the answer:\n"
            "   refund only, replacement only, or both.\n"
            "   Do not call submit_refund until this choice is known.\n"
            "5. Gather a short refund reason from user context if needed.\n"
            "6. If the user wants a refund (refund-only or both),\n"
            "   call submit_refund with order_id, amount (from lookup), and refund_description.\n"
            "7. After approval and successful refund submission:\n"
            "   - If the user explicitly requested replacement/exchange, handoff to order_agent.\n"
            "   - If the user asked for refund only, do not hand off for replacement.\n"
            "     Finalize in this agent and end with exactly: Case complete.\n"
            "8. If the user wants replacement only and no refund, handoff to order_agent directly."
        ),
        client=client,
        tools=[lookup_order_details, submit_refund],
    )

    order = Agent(
        id="order_agent",
        name="order_agent",
        instructions=(
            "You are the order specialist.\n"
            "Only handle replacement/exchange/shipping tasks.\n"
            "1. If replacement intent is confirmed but shipping preference is missing,\n"
            "   ask for shipping preference (standard or expedited).\n"
            "2. If order_id is missing, ask for order_id.\n"
            "3. Once order_id and shipping preference are known,\n"
            "   call submit_replacement(order_id, shipping_preference, replacement_note).\n"
            "4. While the replacement tool call is pending approval, do not claim completion.\n"
            "5. If you receive a submit_replacement function result,\n"
            "   approval has already occurred and submission succeeded.\n"
            "6. Immediately send a final customer-facing confirmation and end with exactly: Case complete.\n"
            "If the user wants refund only and no replacement, do not ask shipping questions.\n"
            "Acknowledge and hand off back to triage_agent for final closure.\n"
            "Do not fabricate tool outputs."
        ),
        client=client,
        tools=[lookup_order_details, submit_replacement],
    )

    return triage, refund, order


def _termination_condition(conversation: list[Message]) -> bool:
    """Stop when any assistant emits an explicit completion marker."""

    for message in reversed(conversation):
        if message.role != "assistant":
            continue
        text = (message.text or "").strip().lower()
        if text.endswith("case complete."):
            return True
    return False


def create_handoff_workflow() -> Workflow:
    """Build the demo HandoffBuilder workflow."""

    triage, refund, order = create_agents()
    builder = HandoffBuilder(
        name="ag_ui_handoff_workflow_demo",
        participants=[triage, refund, order],
        termination_condition=_termination_condition,
    )

    # Explicit handoff topology (instead of default mesh) so routing is enforced in orchestration,
    # not only implied by prompt instructions.
    (
        builder
        .add_handoff(
            triage,
            [refund],
            description="Route when the user requests refunds, damaged-item claims, or refund status updates.",
        )
        .add_handoff(
            triage,
            [order],
            description="Route when the user requests replacement, exchange, shipping preference, or shipment changes.",
        )
        .add_handoff(
            refund,
            [order],
            description="Route after refund work only if replacement/exchange logistics are explicitly needed.",
        )
        .add_handoff(
            refund,
            [triage],
            description="Route back for final case closure when refund-only work is complete.",
        )
        .add_handoff(
            order,
            [triage],
            description="Route back after replacement/shipping tasks are complete for final closure.",
        )
        .add_handoff(
            order,
            [refund],
            description="Route to refund specialist if the user pivots from replacement to refund processing.",
        )
    )

    return builder.with_start_agent(triage).build()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(title="AG-UI Handoff Workflow Demo")

    cors_origins = [
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173").split(",") if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    demo_workflow = AgentFrameworkWorkflow(
        workflow_factory=lambda _thread_id: create_handoff_workflow(),
        name="ag_ui_handoff_workflow_demo",
        description="Dynamic handoff workflow demo with tool approvals and request_info resumes.",
    )

    add_agent_framework_fastapi_endpoint(
        app=app,
        agent=demo_workflow,
        path="/handoff_demo",
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    return app


app = create_app()


def main() -> None:
    """Run the AG-UI demo backend."""

    # Configure logging format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Configure root logger
    logging.basicConfig(level=logging.INFO, format=log_format)

    # Add file handler for persistent logging
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ag_ui_handoff_demo.log")
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10485760,
            backupCount=5,  # 10MB max size, keep 5 backups
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(log_format))

        # Add file handler to root logger
        logging.getLogger().addHandler(file_handler)
        print(f"Logging to file: {log_file}")
    except Exception as e:
        print(f"Warning: Failed to set up file logging: {e}")

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8891"))

    print(f"AG-UI handoff demo backend running at http://{host}:{port}")
    print("AG-UI endpoint: POST /handoff_demo")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
