# Copyright (c) Microsoft. All rights reserved.

"""Agent definitions and AgentCard factories for the A2A server sample.

Provides factory functions to create Agent Framework agents and A2A
AgentCards for the invoice, policy, and logistics agent types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from invoice_data import query_by_invoice_id, query_by_transaction_id, query_invoices

if TYPE_CHECKING:
    from agent_framework import Agent
    from agent_framework.azure import AzureOpenAIResponsesClient


# ---------------------------------------------------------------------------
# Agent instructions
# ---------------------------------------------------------------------------

INVOICE_INSTRUCTIONS = "You specialize in handling queries related to invoices."

POLICY_INSTRUCTIONS = """\
You specialize in handling queries related to policies and customer communications.

Always reply with exactly this text:

Policy: Short Shipment Dispute Handling Policy V2.1

Summary: "For short shipments reported by customers, first verify internal shipment records
(SAP) and physical logistics scan data (BigQuery). If discrepancy is confirmed and logistics data
shows fewer items packed than invoiced, issue a credit for the missing items. Document the
resolution in SAP CRM and notify the customer via email within 2 business days, referencing the
original invoice and the credit memo number. Use the 'Formal Credit Notification' email
template."
"""

LOGISTICS_INSTRUCTIONS = """\
You specialize in handling queries related to logistics.

Always reply with exactly:

Shipment number: SHPMT-SAP-001
Item: TSHIRT-RED-L
Quantity: 900
"""

# ---------------------------------------------------------------------------
# Agent factories
# ---------------------------------------------------------------------------


def create_invoice_agent(client: AzureOpenAIResponsesClient) -> Agent:
    """Create an invoice agent backed by the given client with query tools."""
    return client.as_agent(
        name="InvoiceAgent",
        instructions=INVOICE_INSTRUCTIONS,
        tools=[query_invoices, query_by_transaction_id, query_by_invoice_id],
    )


def create_policy_agent(client: AzureOpenAIResponsesClient) -> Agent:
    """Create a policy agent backed by the given client."""
    return client.as_agent(
        name="PolicyAgent",
        instructions=POLICY_INSTRUCTIONS,
    )


def create_logistics_agent(client: AzureOpenAIResponsesClient) -> Agent:
    """Create a logistics agent backed by the given client."""
    return client.as_agent(
        name="LogisticsAgent",
        instructions=LOGISTICS_INSTRUCTIONS,
    )


# ---------------------------------------------------------------------------
# AgentCard factories
# ---------------------------------------------------------------------------

_CAPABILITIES = AgentCapabilities(streaming=True, push_notifications=False)


def get_invoice_agent_card(url: str) -> AgentCard:
    """Return an A2A AgentCard for the invoice agent."""
    return AgentCard(
        name="InvoiceAgent",
        description="Handles requests relating to invoices.",
        url=url,
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=_CAPABILITIES,
        skills=[
            AgentSkill(
                id="id_invoice_agent",
                name="InvoiceQuery",
                description="Handles requests relating to invoices.",
                tags=["invoice", "agent-framework"],
                examples=["List the latest invoices for Contoso."],
            ),
        ],
    )


def get_policy_agent_card(url: str) -> AgentCard:
    """Return an A2A AgentCard for the policy agent."""
    return AgentCard(
        name="PolicyAgent",
        description="Handles requests relating to policies and customer communications.",
        url=url,
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=_CAPABILITIES,
        skills=[
            AgentSkill(
                id="id_policy_agent",
                name="PolicyAgent",
                description="Handles requests relating to policies and customer communications.",
                tags=["policy", "agent-framework"],
                examples=["What is the policy for short shipments?"],
            ),
        ],
    )


def get_logistics_agent_card(url: str) -> AgentCard:
    """Return an A2A AgentCard for the logistics agent."""
    return AgentCard(
        name="LogisticsAgent",
        description="Handles requests relating to logistics.",
        url=url,
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=_CAPABILITIES,
        skills=[
            AgentSkill(
                id="id_logistics_agent",
                name="LogisticsQuery",
                description="Handles requests relating to logistics.",
                tags=["logistics", "agent-framework"],
                examples=["What is the status for SHPMT-SAP-001"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

AGENT_FACTORIES = {
    "invoice": create_invoice_agent,
    "policy": create_policy_agent,
    "logistics": create_logistics_agent,
}

AGENT_CARD_FACTORIES = {
    "invoice": get_invoice_agent_card,
    "policy": get_policy_agent_card,
    "logistics": get_logistics_agent_card,
}
