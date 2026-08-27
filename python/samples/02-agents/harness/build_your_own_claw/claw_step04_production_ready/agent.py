# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-core",
#     "agent-framework-foundry",
#     "agent-framework-foundry-hosting",
#     "agent-framework-purview",
#     "agent-framework-tools",
#     "agent-framework-monty",
#     "mcp",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

"""Shared production-ready claw agent factory for Post 4.

Builds the same personal finance claw as Step 03 and adds production wiring for
observability-aware hosts plus opt-in Microsoft Purview chat policy middleware.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT       — Microsoft Foundry project endpoint URL
    FOUNDRY_MODEL                  — Model deployment name for local hosts (defaults to gpt-5.4)
    TOOLBOX_MCP_SERVER_URL         — Optional Foundry Toolbox MCP endpoint URL for managed skills
    PURVIEW_CLIENT_APP_ID          — Optional app/client ID; enables Purview chat policy middleware

Run indirectly through a host, for example:
    uv run --prerelease=allow \
        python/samples/02-agents/harness/build_your_own_claw/claw_step04_production_ready/console_app.py
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from agent_framework import (
    Agent,
    AgentModeProvider,
    AggregatingSkillsSource,
    DeduplicatingSkillsSource,
    FileAccessProvider,
    FileSkillsSource,
    FileSystemAgentFileStore,
    HistoryProvider,
    InMemoryHistoryProvider,
    MCPSkillsSource,
    SkillsProvider,
    SkillsSource,
    create_harness_agent,
    tool,
)
from agent_framework.foundry import FoundryChatClient, FoundryToolbox
from agent_framework.microsoft import PurviewChatPolicyMiddleware, PurviewSettings
from agent_framework_monty import MontyCodeActProvider
from agent_framework_tools.shell import LocalShellTool, ShellPolicy
from azure.core.credentials import TokenCredential
from azure.identity import AzureCliCredential, InteractiveBrowserCredential
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from pydantic import Field

# Resolve everything the hosted container needs from this folder. Foundry uses code (ZIP)
# deployment for Python hosted agents and packages *this folder only*, so ``subprocess_script_runner.py``
# and ``skills/`` live beside this file rather than being shared with the parent sample folder.
# ``working/`` (used only by the local file-access and shell hosts) stays in the parent folder: it is
# outside the deployment package and unused on the hosted container, where file access and shell are off.
_SELF_DIR = Path(__file__).resolve().parent
from subprocess_script_runner import subprocess_script_runner  # noqa: E402

_WORKING_DIR = _SELF_DIR.parent / "working"
_VAULT_DIR = _WORKING_DIR / "confirmations"
_SKILLS_DIR = _SELF_DIR / "skills"

# Startup diagnostics go through ``logging``, not ``print``. Foundry hosted agents surface only the
# container's stderr stream, and the agentserver SDK attaches a stderr handler to the root logger —
# so ``print`` (stdout) output is invisible when hosted. See ``hosted.py`` for the matching
# ``logging.basicConfig`` call that has to run before this module builds anything.
logger = logging.getLogger(__name__)

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
    """Get the latest delayed, illustrative stock price and trailing EPS for a ticker symbol."""
    ticker = symbol.upper()
    data = _PRICE_BOOK.get(ticker)
    if data is None:
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
    """Place a simulated buy or sell order; no real order is placed."""
    verb = "Sold" if action == "sell" else "Bought"
    confirmation = f"TRADE-{uuid.uuid4().hex[:8].upper()}"
    return f"{verb} {quantity} share(s) of {symbol.upper()}. Confirmation: {confirmation}."


# </place_trade>


# <skills>
def _require_toolbox_session(toolbox: FoundryToolbox) -> ClientSession:
    """Return the toolbox's live MCP session, or explain why it is not there yet."""
    session = toolbox.session
    if session is None:
        raise RuntimeError(
            "The Foundry Toolbox is not connected, so its skills cannot be read. It is connected by "
            "the agent because it is passed via ``tools=``; make sure that wiring is still in place."
        )
    return session


def _build_skills_provider(credential: TokenCredential) -> tuple[SkillsProvider, list[Any]]:
    """Build local file-based skills plus optional Foundry Toolbox MCP skills.

    Returns the provider and any tools it depends on. ``FoundryToolbox`` is returned as a tool so the
    agent owns its connection lifecycle; it is what authenticates the toolbox and forwards the
    platform's per-request ``x-agent-foundry-call-id``.

    Note that reading a skill's body requires the caller identity to hold the ``Foundry User`` role
    on the Foundry account. Discovery does not, so a missing grant shows up as skills that load and
    advertise fine but fail on first use — see the README.
    """
    sources: list[SkillsSource] = [FileSkillsSource(str(_SKILLS_DIR), script_runner=subprocess_script_runner)]
    tools: list[Any] = []
    logger.info("Local file skills enabled (from %s).", _SKILLS_DIR)

    toolbox_url = os.environ.get("TOOLBOX_MCP_SERVER_URL", "").strip()
    if toolbox_url.startswith(("http://", "https://")):
        # Only the netloc is logged: the full URL carries query parameters.
        toolbox_host = urlsplit(toolbox_url).netloc or "unknown host"
        # ``load_tools=False`` surfaces the toolbox's skills without its tools. The toolbox is still
        # passed to the agent via ``tools=`` because that is what connects the MCP session.
        toolbox = FoundryToolbox(credential, url=toolbox_url, load_tools=False)
        tools.append(toolbox)
        # ``session_provider`` (rather than ``client``) lets the source resolve the session on every
        # discovery and every on-demand fetch, so it survives a toolbox reconnect.
        sources.append(MCPSkillsSource(session_provider=lambda: _require_toolbox_session(toolbox)))
        logger.info("Foundry skills enabled (Toolbox MCP at %s).", toolbox_host)
    elif toolbox_url:
        # A set-but-unusable value is almost always an unsubstituted deployment template placeholder
        # (for example a literal ``{{TOOLBOX_MCP_SERVER_URL}}``). Silently skipping it makes a
        # deployment error look identical to a deliberate opt-out, so warn instead.
        logger.warning(
            "Foundry skills disabled: TOOLBOX_MCP_SERVER_URL is set but is not an http(s) URL (got %r). "
            "If this looks like an unsubstituted placeholder, check the environment variable wiring "
            "in azure.yaml / agent.manifest.yaml.",
            toolbox_url,
        )
    else:
        logger.info("Foundry skills disabled. Set TOOLBOX_MCP_SERVER_URL to enable them.")

    source: SkillsSource = sources[0] if len(sources) == 1 else AggregatingSkillsSource(sources)
    # ``load_skill`` only reads a skill's own body, so gating it behind an approval prompt costs a
    # full round-trip without protecting anything. Approval is kept where it earns its keep: on
    # ``place_trade`` (see its ``approval_mode``) and on ``run_skill_script``, which executes code.
    return SkillsProvider(DeduplicatingSkillsSource(source), disable_load_skill_approval=True), tools


# </skills>


# <background>
def _build_research_agent(client: FoundryChatClient) -> Any:
    """Build the lean web-search-only chat agent used for per-ticker research."""
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
    """Build a sandboxed shell confined to the trade-confirmation vault."""
    return LocalShellTool(
        mode="persistent",
        workdir=str(_VAULT_DIR),
        confine_workdir=True,
        policy=ShellPolicy(
            denylist=[
                r"\brm\s+-rf\b",
                r"\bsudo\b",
                r":\(\)\s*\{",
                r"\bmkfs\b",
                r">\s*/dev/sd",
            ],
        ),
        timeout=15,
    )


# </shell>


def _build_purview_middleware(credential: TokenCredential | None = None) -> list[PurviewChatPolicyMiddleware]:
    """Build opt-in Purview chat middleware from environment variables.

    When ``credential`` is provided (for example the container's managed identity on hosted
    deployments), it is used to authenticate against Purview. Otherwise an
    ``InteractiveBrowserCredential`` is used, which suits local interactive runs.
    """
    client_app_id = os.environ.get("PURVIEW_CLIENT_APP_ID", "").strip()
    if not client_app_id or client_app_id.startswith("{{"):
        logger.info("Purview disabled. Set PURVIEW_CLIENT_APP_ID to enable chat policy enforcement.")
        return []

    purview_credential = credential or InteractiveBrowserCredential(client_id=client_app_id)
    settings = PurviewSettings(app_name="Claw")
    logger.info("Purview enabled (chat policy middleware).")
    return [PurviewChatPolicyMiddleware(purview_credential, settings)]


# <build_claw_agent>
async def build_claw_agent(
    *,
    credential: TokenCredential | None = None,
    project_endpoint: str | None = None,
    model: str | None = None,
    default_options: Mapping[str, Any] | None = None,
    history_provider: HistoryProvider | None = None,
    enable_file_access: bool = True,
    file_access_store: Any = None,
    file_memory_store: Any = None,
    enable_shell: bool = True,
    purview_credential: TokenCredential | None = None,
    auto_approve_skill_scripts: bool = False,
) -> Agent[Any]:
    """Build the production-ready claw harness agent.

    Args:
        credential: Azure credential for the Foundry chat client. Defaults to AzureCliCredential.
        project_endpoint: Optional Foundry project endpoint override.
        model: Optional model deployment override.
        default_options: Optional per-agent default chat options, such as ``{"store": False}`` for hosting.
        history_provider: Optional history provider override. Hosted agents should pass
            ``InMemoryHistoryProvider(load_messages=False)`` because Responses hosting owns history.
        enable_file_access: When True (default), the agent can read and write files. Disable it on
            shared/hosted deployments where arbitrary read/write access to the container filesystem is a
            data-exfiltration and tampering risk; prefer an external ``file_access_store`` instead.
        file_access_store: Optional custom ``AgentFileStore``. When None (and ``enable_file_access`` is
            True), a ``FileSystemAgentFileStore`` rooted at the working dir is used. Supply your own — for
            example, one backed by Azure Blob Storage — to keep files off the container disk when hosted.
        file_memory_store: Optional custom ``AgentFileStore`` backing the harness file memory. When
            None, the harness default is used, which writes to ``{cwd}/agent-file-memory``. Hosted
            deployments must supply a store rooted at a writable path, because the deployed code
            directory is mounted read-only.
        enable_shell: When True (default), the agent can run shell commands. Disable it on
            shared/hosted deployments: arbitrary command execution inside the container is a serious
            security risk (data exfiltration, persistence, tampering) even behind a deny-list.
        purview_credential: Optional credential for Purview chat policy enforcement. Pass the
            container's managed identity (``DefaultAzureCredential``) on hosted deployments; when None,
            an ``InteractiveBrowserCredential`` is used for local interactive runs.
        auto_approve_skill_scripts: When True, ``run_skill_script`` is auto-approved so skills that run
            a bundled script complete without a human in the loop. Intended for unattended runs such as
            ``evals.py``; leave it False for interactive and hosted use. It only covers the skill tools —
            ``place_trade``, the shell, and file writes keep their normal approval behavior.

    Returns:
        A fully configured harness agent with Step 03 capabilities plus opt-in Purview middleware.
    """
    load_dotenv()

    # <create_client>
    resolved_credential = credential or AzureCliCredential()
    client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=model,
        credential=resolved_credential,
        middleware=_build_purview_middleware(purview_credential),
    )
    # </create_client>

    skills_provider, skills_tools = _build_skills_provider(resolved_credential)
    research_agent = _build_research_agent(client)

    if enable_shell:
        # The vault only exists for the local shell host; creating it unconditionally would write
        # outside the deployed package on a hosted container, where shell is off.
        _VAULT_DIR.mkdir(parents=True, exist_ok=True)
        shell = _build_shell()
        logger.info("Shell enabled (confined to the confirmations vault).")
    else:
        shell = None
        logger.info("Shell disabled.")

    if enable_file_access:
        if file_access_store is None:
            # Same reasoning as the vault: only the default local store needs this directory.
            _WORKING_DIR.mkdir(exist_ok=True)
        access_store = file_access_store or FileSystemAgentFileStore(str(_WORKING_DIR))
        logger.info(
            "File access enabled (custom AgentFileStore)."
            if file_access_store is not None
            else "File access enabled (local filesystem)."
        )
    else:
        access_store = None
        logger.info("File access disabled.")

    # <codeact>
    context_providers: list[Any] = [MontyCodeActProvider(approval_mode="never_require")]
    logger.info("CodeAct enabled (Monty).")
    # </codeact>

    auto_approval_rules: list[Any] = [FileAccessProvider.read_only_tools_auto_approval_rule]
    if auto_approve_skill_scripts:
        # Adds ``run_skill_script`` to the auto-approved set. The rule is scoped to the skills
        # provider's own local tools, so it cannot approve anything else.
        auto_approval_rules.append(SkillsProvider.all_tools_auto_approval_rule)
        logger.info("Skill script approval disabled (unattended run).")

    # <create_agent>
    return create_harness_agent(
        client=client,
        name="ClawFinanceAssistant",
        description="Production-ready personal finance claw harness agent.",
        agent_instructions=FINANCE_INSTRUCTIONS,
        tools=[get_stock_price, place_trade, *skills_tools],
        history_provider=history_provider or InMemoryHistoryProvider(),
        file_access_store=access_store,
        file_memory_store=file_memory_store,
        skills_provider=skills_provider,
        background_agents=[research_agent],
        shell_executor=shell,
        auto_approval_rules=auto_approval_rules,
        context_providers=context_providers,
        mode_provider=AgentModeProvider(default_mode="execute"),
        default_options=default_options,
    )
    # </create_agent>
