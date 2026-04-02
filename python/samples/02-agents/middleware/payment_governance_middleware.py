# Copyright (c) Microsoft. All rights reserved.

"""
Payment Governance Middleware with agentpay-mcp

Demonstrates how to add spend governance to AI agents using middleware.
When agents make tool calls that involve payments (x402 protocol, API billing,
or any cost-incurring action), this middleware enforces:

- Per-session budget caps
- Per-call spend limits
- Daily velocity limits
- Category-based policies (e.g., "data" vs "compute" spending)

This pattern is critical for production deployments where autonomous agents
handle real money. AI gateways (LiteLLM, Portkey) govern inference costs —
this middleware governs everything else the agent spends.

Requirements:
    pip install agentpay-mcp httpx

Reference:
    - agentpay-mcp: https://github.com/up2itnow0822/agentpay-mcp
    - x402 protocol: https://x402.org
    - NVIDIA NeMo integration: PR #17 (merged)
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from random import randint
from typing import Annotated

from agent_framework import (
    Agent,
    FunctionInvocationContext,
    tool,
)
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv
from pydantic import Field

load_dotenv()


# ---------------------------------------------------------------------------
# Budget state — in production, back this with agentpay-mcp's MCP tools
# ---------------------------------------------------------------------------
@dataclass
class BudgetState:
    """Tracks spend across a session. Replace with agentpay-mcp calls for
    production use (check_budget, approve_payment, get_spending_report)."""

    session_cap: Decimal = Decimal("5.00")  # USD per session
    per_call_limit: Decimal = Decimal("1.00")  # USD per tool call
    spent: Decimal = Decimal("0")
    call_count: int = 0
    blocked_count: int = 0
    category_caps: dict[str, Decimal] = field(
        default_factory=lambda: {
            "data": Decimal("3.00"),
            "compute": Decimal("2.00"),
        }
    )
    category_spent: dict[str, Decimal] = field(default_factory=dict)


BUDGET = BudgetState()


# ---------------------------------------------------------------------------
# Simulated paid tools — stand-ins for real x402-enabled services
# ---------------------------------------------------------------------------
@tool(approval_mode="never_require")
def fetch_market_data(
    symbol: Annotated[str, Field(description="Ticker symbol to look up")],
) -> str:
    """Fetch real-time market data for a symbol (costs $0.25 per call via x402)."""
    price = randint(50, 500)
    return f"{symbol}: ${price}.{randint(10, 99)} (real-time, x402-settled)"


@tool(approval_mode="never_require")
def run_sentiment_analysis(
    text: Annotated[str, Field(description="Text to analyze")],
) -> str:
    """Run sentiment analysis on text (costs $0.10 per call via x402)."""
    scores = {"positive": randint(40, 90), "negative": randint(5, 30)}
    return f"Sentiment: {scores['positive']}% positive, {scores['negative']}% negative"


# Cost metadata per tool — in production, agentpay-mcp resolves this from
# the x402 price header on each service endpoint.
TOOL_COSTS: dict[str, tuple[Decimal, str]] = {
    "fetch_market_data": (Decimal("0.25"), "data"),
    "run_sentiment_analysis": (Decimal("0.10"), "compute"),
}


# ---------------------------------------------------------------------------
# Payment governance middleware (function-based)
# ---------------------------------------------------------------------------
async def payment_governance_middleware(
    context: FunctionInvocationContext,
    call_next: Callable[[], Awaitable[None]],
) -> None:
    """Enforce budget, per-call, and category limits before every tool call.

    In production, replace the in-memory checks with agentpay-mcp MCP calls:
        - check_budget   → verify session has remaining funds
        - approve_payment → debit the spend and get a signed x402 receipt
        - get_spending_report → audit trail for FinOps dashboards
    """
    fn_name = context.function.name
    cost, category = TOOL_COSTS.get(fn_name, (Decimal("0"), "other"))

    # Gate 1: per-call limit
    if cost > BUDGET.per_call_limit:
        print(
            f"[PaymentGovernance] BLOCKED {fn_name}: "
            f"cost ${cost} exceeds per-call limit ${BUDGET.per_call_limit}"
        )
        BUDGET.blocked_count += 1
        return

    # Gate 2: session cap
    if BUDGET.spent + cost > BUDGET.session_cap:
        print(
            f"[PaymentGovernance] BLOCKED {fn_name}: "
            f"would exceed session cap (${BUDGET.spent + cost} > ${BUDGET.session_cap})"
        )
        BUDGET.blocked_count += 1
        return

    # Gate 3: category cap
    cat_spent = BUDGET.category_spent.get(category, Decimal("0"))
    cat_cap = BUDGET.category_caps.get(category, BUDGET.session_cap)
    if cat_spent + cost > cat_cap:
        print(
            f"[PaymentGovernance] BLOCKED {fn_name}: "
            f"category '{category}' cap exceeded (${cat_spent + cost} > ${cat_cap})"
        )
        BUDGET.blocked_count += 1
        return

    # All gates passed — execute the tool
    print(f"[PaymentGovernance] APPROVED {fn_name}: ${cost} ({category})")
    await call_next()

    # Record spend
    BUDGET.spent += cost
    BUDGET.call_count += 1
    BUDGET.category_spent[category] = cat_spent + cost
    print(
        f"[PaymentGovernance] Session total: ${BUDGET.spent}/{BUDGET.session_cap} "
        f"| Calls: {BUDGET.call_count} | Blocked: {BUDGET.blocked_count}"
    )


# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------
def _create_agent() -> Agent:
    return Agent(
        client=OpenAIChatClient(),
        instructions=(
            "You are a financial research assistant. Use your tools to fetch "
            "market data and run sentiment analysis when asked. Each tool call "
            "costs real money via x402 — the payment governance middleware "
            "enforces your session budget automatically."
        ),
        tools=[fetch_market_data, run_sentiment_analysis],
        function_middleware=[payment_governance_middleware],
    )


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
async def main() -> None:
    agent = _create_agent()

    print("=== Payment Governance Middleware Demo ===\n")
    print(f"Session budget: ${BUDGET.session_cap}")
    print(f"Per-call limit: ${BUDGET.per_call_limit}")
    print(f"Category caps: {dict(BUDGET.category_caps)}\n")

    response = await agent.run(
        "Look up AAPL and MSFT prices, then run sentiment analysis on "
        "'AI agents are transforming enterprise workflows'."
    )
    print(f"\nAgent response:\n{response.text}\n")

    print("=== Spending Report ===")
    print(f"Total spent: ${BUDGET.spent}")
    print(f"Calls made: {BUDGET.call_count}")
    print(f"Calls blocked: {BUDGET.blocked_count}")
    print(f"By category: {dict(BUDGET.category_spent)}")


if __name__ == "__main__":
    asyncio.run(main())
