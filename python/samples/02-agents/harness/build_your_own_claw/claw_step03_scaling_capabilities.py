# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework",
#     "agent-framework-tools",
#     "agent-framework-monty",
#     "mcp",
#     "httpx",
#     "textual>=6.2.1",
#     "rich>=13.7.1",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run python/samples/02-agents/harness/build_your_own_claw/claw_step03_scaling_capabilities.py

# Copyright (c) Microsoft. All rights reserved.

"""Scaling its capabilities (Post 3) — Python.

The third runnable sample from the "Build your own claw and agent harness with Microsoft Agent
Framework" blog series. See: https://devblogs.microsoft.com/agent-framework/agent-harness-scaling-its-capabilities.
It builds on Post 2's personal finance assistant and makes it *more capable* in four ways:

1. Skills        — package finance know-how (valuation, risk-scoring) as discoverable SKILL.md
                   files the agent loads on demand. Optionally fold in centrally-managed Foundry
                   skills served from a Foundry Toolbox MCP endpoint (opt-in via
                   FOUNDRY_TOOLBOX_MCP_SERVER_URL).
2. Shell         — a sandboxed shell, confined to the trade-confirmation vault, that the agent uses
                   to reorganize the accumulated confirmation files (year/month, rename, archive).
                   Guarded by an allow/deny-list policy and a confined working directory.
3. CodeAct       — the agent writes and runs Python to crunch portfolio numbers, using the
                   cross-platform Monty interpreter.
4. Background agents — fan out a per-ticker research sub-agent so several tickers are researched
                   concurrently, then aggregated.

This sample reuses the shared harness ``console`` package in the parent ``harness/`` directory.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT       — Microsoft Foundry project endpoint URL
    FOUNDRY_MODEL                  — Model deployment name (defaults to gpt-5.4)
    FOUNDRY_TOOLBOX_MCP_SERVER_URL — (optional) Foundry Toolbox MCP endpoint URL; enables Foundry skills

Authentication:
    Run ``az login`` before running this sample.
"""

import asyncio
import os
import sys
import uuid
from collections.abc import Callable, Generator
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from agent_framework import (
    AggregatingSkillsSource,
    Agent,
    AgentModeProvider,
    DeduplicatingSkillsSource,
    FileAccessProvider,
    FileSkillsSource,
    FileSystemAgentFileStore,
    MCPSkillsSource,
    SkillsProvider,
    SkillsSource,
    create_harness_agent,
    tool,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework_monty import MontyCodeActProvider
from agent_framework_tools.shell import LocalShellTool, ShellPolicy
from azure.identity import AzureCliCredential, get_bearer_token_provider
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import Field

# Reuse the shared harness console that lives in the parent ``harness/`` directory, and the local
# subprocess script runner used to execute file-based skill scripts.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from console import build_observers_with_planning, run_agent_async  # noqa: E402

from subprocess_script_runner import subprocess_script_runner  # noqa: E402

_SAMPLE_DIR = Path(__file__).resolve().parent
_WORKING_DIR = _SAMPLE_DIR / "working"
_VAULT_DIR = _WORKING_DIR / "confirmations"
_SKILLS_DIR = _SAMPLE_DIR / "skills"

FINANCE_INSTRUCTIONS = """\
## Personal Finance Assistant Instructions

You are a personal finance and investing assistant. You help the user understand their portfolio
and watchlist, value individual stocks, gauge portfolio risk, research the market, and keep their
records tidy.

### Working style

- The user's holdings live in a file called portfolio.csv. Read it with the file_access tools
  before answering questions about their portfolio, and never modify it unless asked.
- You have skills for valuation and risk-scoring. When a question matches a skill, load it and
  follow its instructions (read its references, run its scripts) rather than guessing.
- When asked to research several tickers, delegate each one to the background research agent so
  they run concurrently, then summarize the findings together.
- The user's trade confirmations accumulate in the working/confirmations folder. When asked to tidy
  or reorganize them, use the run_shell tool: inspect the folder first, then move files into a
  year/month layout and rename them to YYYY-MM-DD_TICKER_BUY|SELL.txt. Explain your plan before
  running commands that change anything.
- To buy or sell, use the place_trade tool. This takes a real action, so the user will be asked to
  approve it before it runs — explain what you are about to do first.

### Important

You provide information and analysis only — you are not a licensed financial advisor and you must
not present your output as personalized investment advice. Remind the user to do their own
research before making decisions.
"""

# A tiny in-memory book of (price, trailing EPS) so the sample runs without any external dependency.
# These are illustrative mock values, not real market data.
_PRICE_BOOK: dict[str, tuple[float, float]] = {
    "MSFT": (462.97, 11.80),
    "AAPL": (229.35, 6.13),
    "GOOGL": (178.12, 7.54),
    "AMZN": (201.45, 4.18),
    "NVDA": (134.81, 2.95),
    "SPY": (612.40, 23.10),
}


# <get_stock_price>
def get_stock_price(
    symbol: Annotated[str, "The stock ticker symbol, e.g. MSFT or AAPL."],
) -> dict[str, object]:
    """Get the latest (delayed, illustrative) stock price and trailing EPS for a ticker symbol."""
    ticker = symbol.upper()
    data = _PRICE_BOOK.get(ticker)
    if data is None:
        # Deterministic pseudo-values for unknown symbols so the sample stays self-contained.
        # The built-in hash() is randomized per process (PYTHONHASHSEED), so derive a stable seed.
        seed = 0
        for ch in ticker:
            seed = (seed * 31 + ord(ch)) % 1_000_000
        price = 50.0 + (seed % 45000) / 100.0
        data = (price, round(price / 20.0, 2))

    return {
        "symbol": ticker,
        "price": round(data[0], 2),
        "trailing_eps": round(data[1], 2),
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


# <skills>
async def _build_skills_provider(stack: AsyncExitStack) -> SkillsProvider:
    """Build a skills provider over the local skills/ folder, plus optional Foundry-managed skills.

    File-based skills (valuation, risk-scoring) always load. When FOUNDRY_TOOLBOX_MCP_SERVER_URL is
    set we also connect to a Foundry Toolbox MCP endpoint and surface its skills, so they can be
    managed and updated centrally without changing this agent.
    """
    # subprocess_script_runner lets the file-based skills run their Python scripts.
    sources: list[SkillsSource] = [FileSkillsSource(str(_SKILLS_DIR), script_runner=subprocess_script_runner)]

    toolbox_url = os.environ.get("FOUNDRY_TOOLBOX_MCP_SERVER_URL")
    if toolbox_url:
        session = await _connect_foundry_toolbox(stack, toolbox_url)
        sources.append(MCPSkillsSource(client=session))
        print("Foundry skills enabled (Toolbox MCP).")
    else:
        print("Foundry skills disabled. Set FOUNDRY_TOOLBOX_MCP_SERVER_URL to enable them.")

    source: SkillsSource = sources[0] if len(sources) == 1 else AggregatingSkillsSource(sources)
    return SkillsProvider(DeduplicatingSkillsSource(source))


class _ToolboxAuth(httpx.Auth):
    """Attach a fresh Foundry bearer token to every request."""

    def __init__(self, token_provider: Callable[[], str]):
        self._get_token = token_provider

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


async def _connect_foundry_toolbox(stack: AsyncExitStack, url: str) -> ClientSession:
    """Open an MCP session against a Foundry Toolbox endpoint, tied to ``stack``'s lifetime."""
    token_provider = get_bearer_token_provider(AzureCliCredential(), "https://ai.azure.com/.default")
    http_client = await stack.enter_async_context(
        httpx.AsyncClient(
            auth=_ToolboxAuth(token_provider),
            headers={"Foundry-Features": "Toolboxes=V1Preview"},
            timeout=httpx.Timeout(30.0, read=300.0),
            follow_redirects=True,
        )
    )
    read, write, _ = await stack.enter_async_context(streamable_http_client(url=url, http_client=http_client))
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return session
# </skills>


# <background>
def _build_research_agent(client: FoundryChatClient) -> Any:
    """Build the lean, web-search-only chat agent used for per-ticker research."""
    # This sub-agent doesn't need any harness machinery - it's a plain chat agent with a single
    # tool: the same hosted web search the harness would have added. The parent still exposes the
    # background_agents_* tools because it receives this agent via background_agents.
    return Agent(
        client=client,
        name="TickerResearchAgent",
        description="Searches the web for recent news and commentary about a single stock ticker.",
        tools=[client.get_web_search_tool()],
        instructions=(
            "You research a single stock ticker. Use the web search tool to find the most recent, "
            "relevant news and commentary, then return a short, factual summary (3-4 bullet points) "
            "with no preamble."
        ),
    )
# </background>


# <shell>
def _build_shell() -> LocalShellTool:
    """A sandboxed shell, confined to the trade-confirmation vault.

    ``confine_workdir`` re-anchors every command to the vault, and the deny-list pre-filters
    obviously destructive command shapes. (Patterns are a UX guardrail, not a security boundary —
    for hard isolation use DockerShellTool.) Left at the default ``approval_mode="always_require"``
    so each command is surfaced for approval.
    """
    return LocalShellTool(
        mode="persistent",
        workdir=str(_VAULT_DIR),
        confine_workdir=True,
        policy=ShellPolicy(
            denylist=[
                r"\brm\s+-rf\b",
                r"\bsudo\b",
                r":\(\)\s*\{",  # fork-bomb shape
                r"\bmkfs\b",
                r">\s*/dev/sd",
            ],
        ),
        timeout=15,
    )
# </shell>


async def main() -> None:
    load_dotenv()
    _WORKING_DIR.mkdir(exist_ok=True)

    # <create_client>
    # Construct a chat client (see Post 1). FoundryChatClient reads FOUNDRY_PROJECT_ENDPOINT and
    # FOUNDRY_MODEL from the environment; AzureCliCredential handles auth (run `az login`).
    client = FoundryChatClient(credential=AzureCliCredential())
    # </create_client>

    async with AsyncExitStack() as stack:
        skills_provider = await _build_skills_provider(stack)
        research_agent = _build_research_agent(client)
        shell = _build_shell()

        # <codeact>
        # CodeAct: a sandboxed Python interpreter the model can write and run code in to crunch
        # numbers. Monty is a pure, cross-platform interpreter, so it needs no extra setup.
        context_providers: list[Any] = [MontyCodeActProvider(approval_mode="never_require")]
        print("CodeAct enabled (Monty).")
        # </codeact>

        # <create_agent>
        # Turn the chat client into a harness agent. On top of Post 2's file access and approvals we
        # add the four "scaling" capabilities: skills (our own provider), background agents, a
        # confined shell, and optional CodeAct. Read-only file tools are auto-approved so reading the
        # portfolio is frictionless while writes, trades, and shell commands still prompt.
        agent = create_harness_agent(
            client=client,
            agent_instructions=FINANCE_INSTRUCTIONS,
            tools=[get_stock_price, place_trade],
            file_access_store=FileSystemAgentFileStore(str(_WORKING_DIR)),
            skills_provider=skills_provider,
            background_agents=[research_agent],
            shell_executor=shell,
            auto_approval_rules=[FileAccessProvider.read_only_tools_auto_approval_rule],
            context_providers=context_providers,
            mode_provider=AgentModeProvider(default_mode="execute"),
        )
        # </create_agent>

        # <run>
        session = agent.create_session()

        # Run the interactive console session. The default planning observers already include a tool
        # approval observer, so the place_trade and run_shell approval prompts are surfaced
        # automatically.
        await run_agent_async(
            agent,
            session=session,
            observers=build_observers_with_planning(agent),
            initial_mode="execute",
            title="💹 Finance Assistant",
            placeholder="Value a stock, score your portfolio risk, research tickers, or tidy your confirmations...",
        )
        # </run>


if __name__ == "__main__":
    asyncio.run(main())
