# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework",
#     "azure-ai-projects",
#     "textual>=6.2.1",
#     "rich>=13.7.1",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run python/samples/02-agents/harness/build_your_own_claw/claw_step02_working_with_data.py

# Copyright (c) Microsoft. All rights reserved.

"""Working with your data, safely (Post 2) — Python.

The second runnable sample from the "Build your own claw and agent harness with Microsoft Agent
Framework" blog series. See: https://devblogs.microsoft.com/agent-framework/agent-harness-working-with-your-data-safely.
It builds on Post 1's personal finance assistant and adds three abilities:

1. File access  — read the user's ``portfolio.csv`` and write report files (file_access_* tools),
                  on by default in the harness. Read-only file tools are auto-approved; writes
                  still prompt.
2. Approvals    — the ``place_trade`` tool is marked ``approval_mode="always_require"`` so the
                  harness asks for human approval before it runs.
3. Durable memory, two complementary kinds:
     * File memory   (coarse-grained, explicit) — the agent reads/writes files like
                     ``watchlist.md``. On by default. Its files live on disk under
                     ``{cwd}/agent-file-memory/<session-id>/``, so they persist across runs on this
                     machine. A new session starts empty; ``/session-export`` + ``/session-import``
                     preserve the session id so a relaunched session re-links to its memory files.
     * Foundry memory (fine-grained, automatic) — Microsoft Foundry extracts durable facts (e.g.
                     the user's risk tolerance) from the conversation. Opt-in: enabled only when
                     FOUNDRY_MEMORY_STORE and FOUNDRY_EMBEDDING_MODEL are set.

This sample reuses the shared harness ``console`` package in the parent ``harness/`` directory.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Microsoft Foundry project endpoint URL
    FOUNDRY_MODEL            — Model deployment name (defaults to gpt-5.4)
    FOUNDRY_MEMORY_STORE     — (optional) Foundry memory store name; enables Foundry memory
    FOUNDRY_EMBEDDING_MODEL  — (optional) embedding deployment; required for Foundry memory

Authentication:
    Run ``az login`` before running this sample.
"""

import asyncio
import os
import sys
import uuid
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from agent_framework import (
    AgentModeProvider,
    FileAccessProvider,
    FileSystemAgentFileStore,
    create_harness_agent,
    tool,
)
from agent_framework.foundry import FoundryChatClient, FoundryMemoryProvider
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

# Reuse the shared harness console that lives in the parent ``harness/`` directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from console import build_observers_with_planning, run_agent_async  # noqa: E402

# Fixed folder so file access (portfolio.csv, reports) lives next to this script. File memory uses its
# on-disk default ({cwd}/agent-file-memory/<session-id>/), so memory files persist across runs on this
# machine; /session-export + /session-import preserve the session id so a relaunch re-links to them.
_SAMPLE_DIR = Path(__file__).resolve().parent
_WORKING_DIR = _SAMPLE_DIR / "working"
# Foundry memory is scoped to a single logical user here, so its facts are recalled across sessions.
# In a real world scenario, "claw-sample-user" should be replaced with a unique identifier
# for the active user.
# To tie memories to the session instead, just don't pass a scope, and the provider will default
# to session scoped.
_MEMORY_SCOPE = "claw-sample-user"

FINANCE_INSTRUCTIONS = """\
## Personal Finance Assistant Instructions

You are a personal finance and investing assistant. You help the user understand their portfolio
and watchlist, and you can place trades on their behalf.

### Working style

- The user's holdings live in a file called portfolio.csv. Read it with the file_access tools
  before answering questions about their portfolio, and never modify it unless asked.
- When asked for a report or analysis, write it to a Markdown file with the file_access tools
  (e.g. reports/portfolio-review.md) and tell the user where you saved it.
- Keep the user's watchlist in a memory file called watchlist.md: read it when reviewing the
  watchlist, and update it whenever the user adds or removes a ticker.
- To buy or sell, use the place_trade tool. This takes a real action, so the user will be asked to
  approve it before it runs — explain what you are about to do first.
- Remember durable facts the user tells you about themselves (risk tolerance, goals, preferences)
  and take them into account when giving analysis.

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
    "SPY": 612.40,
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


# <place_trade>
@tool(approval_mode="always_require")
def place_trade(
    symbol: Annotated[str, "The stock ticker symbol to trade, e.g. MSFT."],
    action: Annotated[Literal["buy", "sell"], "Either 'buy' or 'sell'."],
    quantity: Annotated[int, Field(gt=0, description="The number of shares to trade.")],
) -> str:
    """Place a (simulated) buy or sell order. Marked approval-required, so the harness asks the
    user to approve before this ever runs. No real order is placed.

    ``action`` and ``quantity`` are validated by the framework (pydantic) from their type hints:
    the model can only pass 'buy'/'sell' and a quantity greater than zero.
    """
    verb = "Sold" if action == "sell" else "Bought"
    confirmation = f"TRADE-{uuid.uuid4().hex[:8].upper()}"
    return f"{verb} {quantity} share(s) of {symbol.upper()}. Confirmation: {confirmation}."
# </place_trade>


# <memory>
async def _maybe_enable_foundry_memory(stack: AsyncExitStack) -> FoundryMemoryProvider | None:
    """Enable fine-grained Foundry memory when configured, otherwise return None.

    Foundry memory needs a memory store and an embedding model, so it is opt-in. When the required
    environment variables are present we (best-effort) create the store and return a provider
    scoped to a single user, so extracted facts are recalled across sessions.
    """
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    store_name = os.environ.get("FOUNDRY_MEMORY_STORE")
    embedding_model = os.environ.get("FOUNDRY_EMBEDDING_MODEL")
    chat_model = os.environ.get("FOUNDRY_MODEL", "gpt-5.4")

    if not (endpoint and store_name and embedding_model):
        print("Foundry memory disabled. Set FOUNDRY_MEMORY_STORE and FOUNDRY_EMBEDDING_MODEL to enable it.")
        return None

    # Imported lazily so the common (file-memory-only) path has no async-project dependency.
    from azure.ai.projects.aio import AIProjectClient
    from azure.ai.projects.models import MemoryStoreDefaultDefinition, MemoryStoreDefaultOptions
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential

    credential = await stack.enter_async_context(AsyncAzureCliCredential())
    project_client = await stack.enter_async_context(AIProjectClient(endpoint=endpoint, credential=credential))

    # Create the memory store only if it does not already exist.
    try:
        await project_client.beta.memory_stores.get(name=store_name)
        print(f"Using existing memory store '{store_name}'.")
    except ResourceNotFoundError:
        definition = MemoryStoreDefaultDefinition(
            chat_model=chat_model,
            embedding_model=embedding_model,
            options=MemoryStoreDefaultOptions(chat_summary_enabled=False, user_profile_enabled=True),
        )
        await project_client.beta.memory_stores.create(
            name=store_name,
            description="Durable memory for the Build-your-own-claw finance assistant.",
            definition=definition,
        )
        print(f"Created memory store '{store_name}'.")

    provider = FoundryMemoryProvider(
        project_client=project_client,
        memory_store_name=store_name,
        scope=_MEMORY_SCOPE,
        update_delay=0,  # Update memories immediately (demo). In production, batch with a delay.
    )
    print(f"Foundry memory enabled (store: {store_name}).")
    return provider
# </memory>


async def main() -> None:
    load_dotenv()
    _WORKING_DIR.mkdir(exist_ok=True)

    # <create_client>
    # Construct a chat client (see Post 1). FoundryChatClient reads FOUNDRY_PROJECT_ENDPOINT and
    # FOUNDRY_MODEL from the environment; AzureCliCredential handles auth (run `az login`).
    client = FoundryChatClient(credential=AzureCliCredential())
    # </create_client>

    async with AsyncExitStack() as stack:
        # <foundry_memory>
        # Fine-grained, automatic memory (when configured) is just another context provider.
        context_providers: list[Any] = []
        foundry_memory = await _maybe_enable_foundry_memory(stack)
        if foundry_memory is not None:
            context_providers.append(foundry_memory)
        # </foundry_memory>

        # <create_agent>
        # Turn the chat client into a harness agent. On top of Post 1's defaults we point file
        # access at a folder next to this script, add our approval-gated place_trade tool,
        # auto-approve the read-only file tools (so reading is frictionless while writes and
        # trades still prompt), and optionally add the Foundry memory provider. File memory keeps its
        # on-disk default store, and we don't point it at a custom folder here. We default the agent to
        # execute mode (autonomous); the user can still switch to plan with the `mode_set` tool.
        agent = create_harness_agent(
            client=client,
            agent_instructions=FINANCE_INSTRUCTIONS,
            tools=[get_stock_price, place_trade],
            file_access_store=FileSystemAgentFileStore(str(_WORKING_DIR)),
            auto_approval_rules=[FileAccessProvider.read_only_tools_auto_approval_rule],
            context_providers=context_providers or None,
            mode_provider=AgentModeProvider(default_mode="execute"),
        )
        # </create_agent>

        # <run>
        session = agent.create_session()

        # Run the interactive console session. The default planning observers already include a
        # tool approval observer, so the place_trade approval prompt is surfaced automatically.
        await run_agent_async(
            agent,
            session=session,
            observers=build_observers_with_planning(agent),
            initial_mode="execute",
            title="💹 Finance Assistant",
            placeholder="Review your portfolio, draft a report, update your watchlist, or place a trade...",
        )
        # </run>


if __name__ == "__main__":
    asyncio.run(main())
