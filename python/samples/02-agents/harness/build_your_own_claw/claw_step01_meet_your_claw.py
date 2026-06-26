# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework",
#     "textual>=6.2.1",
#     "rich>=13.7.1",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run python/samples/02-agents/harness/build_your_own_claw/claw_step01_meet_your_claw.py

# Copyright (c) Microsoft. All rights reserved.

"""Meet your agent harness and claw (Post 1) — Python.

The first runnable sample from the "Build your own claw with Microsoft Agent Framework" blog
series. See: https://devblogs.microsoft.com/agent-framework/meet-your-agent-harness-and-claw.
It builds the foundation of a personal finance / investing assistant on top of
``create_harness_agent``.

``create_harness_agent`` is a factory that wires up a batteries-included agent: function
invocation, per-service-call history persistence, planning (TodoProvider +
AgentModeProvider), and web search. All we add here is finance-focused
instructions and a custom ``get_stock_price`` tool.

This sample reuses the shared harness ``console`` package that lives in the parent
``harness/`` directory.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Microsoft Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name

Authentication:
    Run ``az login`` before running this sample.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from agent_framework import create_harness_agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Reuse the shared harness console that lives in the parent ``harness/`` directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from console import build_observers_with_planning, run_agent_async  # noqa: E402

FINANCE_INSTRUCTIONS = """\
## Personal Finance Assistant Instructions

You are a personal finance and investing assistant. You help the user understand their watchlist
and the markets. When asked about a stock, look up its current price with the get_stock_price
tool, and use web search for recent news, earnings, or analyst commentary.

### Working style

- Always verify numbers with a tool rather than relying on memory. Stock prices change.
- Cite web sources inline when you use them.
- Keep the user's watchlist in a memory file called watchlist.md: read it when reviewing the
  watchlist, and update it whenever the user adds or removes a ticker.

### Important

You provide information and analysis only — you are not a licensed financial advisor and you must
not present your output as personalized investment advice. Remind the user to do their own
research before making decisions.
"""

# A tiny in-memory price book so the sample runs without any external dependency.
# These are illustrative mock prices, not real market quotes.
_PRICE_BOOK: dict[str, float] = {
    "MSFT": 462.97,
    "AAPL": 229.35,
    "GOOGL": 178.12,
    "AMZN": 201.45,
    "NVDA": 134.81,
}


# <get_stock_price>
def get_stock_price(
    symbol: Annotated[str, "The stock ticker symbol, e.g. MSFT or AAPL."],
) -> dict[str, object]:
    """Get the latest (delayed, illustrative) stock price for a ticker symbol."""
    ticker = symbol.upper()
    price = _PRICE_BOOK.get(ticker)
    if price is None:
        # Deterministic pseudo-price for unknown symbols so the sample stays self-contained.
        # Derive a stable seed from the characters — the built-in hash() is randomized per
        # process (PYTHONHASHSEED), so it would give different prices on every run.
        seed = 0
        for ch in ticker:
            seed = (seed * 31 + ord(ch)) % 1_000_000
        price = 50.0 + (seed % 45000) / 100.0

    return {
        "symbol": ticker,
        "price": round(price, 2),
        "currency": "USD",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
# </get_stock_price>


async def main() -> None:
    load_dotenv()

    # <create_client>
    # Construct a chat client. FoundryChatClient reads FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL
    # from the environment; AzureCliCredential handles auth (run `az login`, or swap in another
    # credential). The harness works with ANY chat client — see the providers samples for OpenAI,
    # Azure OpenAI, Anthropic, Ollama, and more.
    client = FoundryChatClient(credential=AzureCliCredential())
    # </create_client>

    # <create_agent>
    # Turn the chat client into a harness agent with finance instructions and our custom
    # stock-price tool. Planning (todo + mode) and web search are configured automatically.
    agent = create_harness_agent(
        client=client,
        agent_instructions=FINANCE_INSTRUCTIONS,
        tools=get_stock_price,
    )
    # </create_agent>

    # <run>
    # Run the interactive console session using the shared harness console helper.
    await run_agent_async(
        agent,
        session=agent.create_session(),
        observers=build_observers_with_planning(agent),
        initial_mode="plan",
        title="💹 Finance Assistant",
        placeholder="Ask about a stock or say 'review my watchlist'...",
    )
    # </run>


if __name__ == "__main__":
    asyncio.run(main())
