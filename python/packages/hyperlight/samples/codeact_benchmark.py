# Copyright (c) Microsoft. All rights reserved.

"""Benchmark CodeAct vs. traditional tool-calling for a multi-tool-call task.

This sample runs the same prompt against the same FoundryChatClient twice:

1. **Traditional tool-calling**: the five business tools are passed directly to
   the agent, so the model calls each tool individually via the LLM tool-call
   interface.
2. **CodeAct**: the same tools are registered on a HyperlightCodeActProvider
   and the model sees a single ``execute_code`` tool that calls them from
   inside the Hyperlight sandbox via ``call_tool(...)``.

The task (computing grand totals per user) naturally requires many tool calls
to complete. At the end, the sample prints elapsed time and token usage for
each run so the two approaches can be compared.

Run with:
    cd python
    uv run --directory packages/hyperlight python samples/codeact_benchmark.py

Required environment variables (loaded from ``.env`` if present):
    FOUNDRY_PROJECT_ENDPOINT
    FOUNDRY_MODEL
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Annotated, Any, Literal

from agent_framework import Agent, AgentResponse, UsageDetails
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from agent_framework_hyperlight import HyperlightCodeActProvider

load_dotenv()


# 1. Deterministic "business" data and tools.

_USERS: list[dict[str, Any]] = [
    {"id": 1, "name": "Alice", "region": "EU", "tier": "gold"},
    {"id": 2, "name": "Bob", "region": "US", "tier": "silver"},
    {"id": 3, "name": "Charlie", "region": "US", "tier": "gold"},
    {"id": 4, "name": "Diana", "region": "APAC", "tier": "bronze"},
    {"id": 5, "name": "Evan", "region": "EU", "tier": "silver"},
    {"id": 6, "name": "Fiona", "region": "US", "tier": "gold"},
    {"id": 7, "name": "George", "region": "APAC", "tier": "gold"},
    {"id": 8, "name": "Hana", "region": "EU", "tier": "bronze"},
]

_ORDERS: dict[int, list[dict[str, Any]]] = {
    1: [{"product": "Widget", "qty": 3, "unit_price": 9.99}, {"product": "Gadget", "qty": 1, "unit_price": 19.99}],
    2: [{"product": "Widget", "qty": 1, "unit_price": 9.99}],
    3: [{"product": "Gadget", "qty": 2, "unit_price": 19.99}, {"product": "Thingamajig", "qty": 4, "unit_price": 4.50}],
    4: [{"product": "Widget", "qty": 10, "unit_price": 9.99}],
    5: [{"product": "Gadget", "qty": 1, "unit_price": 19.99}],
    6: [{"product": "Widget", "qty": 2, "unit_price": 9.99}, {"product": "Thingamajig", "qty": 5, "unit_price": 4.50}],
    7: [{"product": "Gadget", "qty": 3, "unit_price": 19.99}],
    8: [{"product": "Thingamajig", "qty": 2, "unit_price": 4.50}],
}

_DISCOUNTS: dict[str, float] = {"gold": 0.20, "silver": 0.10, "bronze": 0.05}
_TAX_RATES: dict[str, float] = {"EU": 0.21, "US": 0.08, "APAC": 0.10}


def list_users() -> list[dict[str, Any]]:
    """Return all users as a list of dictionaries.

    Each entry has keys: id (int), name (str), region (str), tier (str).
    """
    return _USERS


def get_orders_for_user(
    user_id: Annotated[int, "The user id whose orders to retrieve."],
) -> list[dict[str, Any]]:
    """Return the user's orders as a list of dictionaries.

    Each entry has keys: product (str), qty (int), unit_price (float).
    """
    return _ORDERS.get(user_id, [])


def get_discount_rate(
    tier: Annotated[Literal["gold", "silver", "bronze"], "The customer tier."],
) -> float:
    """Return the discount rate as a float fraction (e.g. 0.2 for 20%)."""
    return _DISCOUNTS[tier]


def get_tax_rate(
    region: Annotated[Literal["EU", "US", "APAC"], "The region code."],
) -> float:
    """Return the tax rate as a float fraction (e.g. 0.21 for 21%)."""
    return _TAX_RATES[region]


def compute_line_total(
    qty: Annotated[int, "Line item quantity."],
    unit_price: Annotated[float, "Line item unit price."],
    discount_rate: Annotated[float, "Discount rate as a fraction (e.g. 0.2 for 20%)."],
    tax_rate: Annotated[float, "Tax rate as a fraction (e.g. 0.21 for 21%)."],
) -> float:
    """Compute a single order line total.

    Formula: qty * unit_price * (1 - discount_rate) * (1 + tax_rate), rounded to 2 decimals.
    """
    subtotal = qty * unit_price
    discounted = subtotal * (1.0 - discount_rate)
    return round(discounted * (1.0 + tax_rate), 2)


TOOLS = [list_users, get_orders_for_user, get_discount_rate, get_tax_rate, compute_line_total]


# 2. Structured output schema shared between both runs.


class UserTotal(BaseModel):
    """A user's grand total of all their orders."""

    user_id: int = Field(description="The user's id.")
    name: str = Field(description="The user's display name.")
    grand_total: float = Field(description="Sum of all line totals, rounded to 2 decimals.")


class UserGrandTotals(BaseModel):
    """Structured output schema for both runs."""

    results: list[UserTotal] = Field(description="One entry per user, sorted by grand_total descending.")


INSTRUCTIONS = "You are a careful assistant. Use the provided tools for every lookup and computation."

BENCHMARK_PROMPT = (
    "For every user in our system (there are 8 of them), compute the grand total of all their orders. "
    "Use the compute_line_total tool for each user's orders, after looking up the relevant discount and "
    "tax rates for that user. "
    "Use the provided tools for EVERY data lookup (users, orders, discount rates, tax rates) and for EVERY "
    "line-total computation via compute_line_total — do not invent values or hardcode any numbers. "
    "The total per order item should apply the discount first and then the tax "
    "(e.g. total = qty * unit_price * (1-discount) * (1+tax)). "
    "Return one entry per user, sorted by grand_total descending."
)


def get_client() -> FoundryChatClient:
    """Create a FoundryChatClient from environment variables."""
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )


# 3. Two runners that share the same tools, prompt, and structured output schema.


async def _run_traditional() -> tuple[float, AgentResponse]:
    agent = Agent(
        client=get_client(),
        name="TraditionalAgent",
        instructions=INSTRUCTIONS,
        tools=TOOLS,
        default_options={"response_format": UserGrandTotals},
    )
    start = time.perf_counter()
    result = await agent.run(BENCHMARK_PROMPT)
    elapsed = time.perf_counter() - start
    return elapsed, result


async def _run_codeact() -> tuple[float, AgentResponse]:
    codeact = HyperlightCodeActProvider(
        tools=TOOLS,
        approval_mode="never_require",
    )
    agent = Agent(
        client=get_client(),
        name="CodeActAgent",
        instructions=INSTRUCTIONS,
        context_providers=[codeact],
        default_options={"response_format": UserGrandTotals},
    )
    start = time.perf_counter()
    result = await agent.run(BENCHMARK_PROMPT)
    elapsed = time.perf_counter() - start
    return elapsed, result


# 4. Report results side by side.


def _print_section(title: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n{title}\n{bar}")


def _format_usage(usage: UsageDetails | None) -> str:
    if usage is None:
        return "usage=<none>"
    return (
        f"input={usage.get('input_token_count') or 0:>6} "
        f"output={usage.get('output_token_count') or 0:>6} "
        f"total={usage.get('total_token_count') or 0:>6}"
    )


def _print_results(result: AgentResponse) -> None:
    if result.value is not None:
        for row in result.value.results:
            print(f"  user_id={row.user_id:>2}  name={row.name:<8}  grand_total={row.grand_total:>8.2f}")
    else:
        print(result.text)


async def main() -> None:
    """Run the benchmark and print a comparison."""
    trad_time, trad_result = await _run_traditional()
    code_time, code_result = await _run_codeact()

    _print_section("Traditional tool-calling")
    print(f"time={trad_time:7.2f}s  {_format_usage(trad_result.usage_details)}")
    _print_results(trad_result)

    _print_section("CodeAct (HyperlightCodeActProvider)")
    print(f"time={code_time:7.2f}s  {_format_usage(code_result.usage_details)}")
    _print_results(code_result)

    _print_section("Comparison")
    trad_total = (trad_result.usage_details or {}).get("total_token_count") or 0
    code_total = (code_result.usage_details or {}).get("total_token_count") or 0

    def pct(new: float, old: float) -> str:
        if old == 0:
            return "n/a"
        delta = (new - old) / old * 100
        sign = "+" if delta >= 0 else ""
        return f"{sign}{delta:.1f}%"

    print(f"time   : traditional={trad_time:7.2f}s   codeact={code_time:7.2f}s   delta={pct(code_time, trad_time)}")
    print(f"tokens : traditional={trad_total:7d}    codeact={code_total:7d}    delta={pct(code_total, trad_total)}")


if __name__ == "__main__":
    asyncio.run(main())
