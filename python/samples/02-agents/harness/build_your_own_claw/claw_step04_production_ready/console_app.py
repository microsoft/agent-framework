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
#     "httpx",
#     "textual>=6.2.1",
#     "rich>=13.7.1",
#     "azure-identity",
#     "python-dotenv",
#     "opentelemetry-api",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

"""Interactive local host for the production-ready claw.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT       — Microsoft Foundry project endpoint URL
    FOUNDRY_MODEL                  — Model deployment name (defaults to gpt-5.4)
    TOOLBOX_MCP_SERVER_URL         — Optional Foundry Toolbox MCP endpoint URL
    PURVIEW_CLIENT_APP_ID          — Optional app/client ID; enables Purview
    ENABLE_INSTRUMENTATION         — Controls Agent Framework instrumentation
    ENABLE_SENSITIVE_DATA          — Enables sensitive telemetry capture when true
    ENABLE_CONSOLE_EXPORTERS       — Enables console OpenTelemetry exporters when true
    OTEL_EXPORTER_OTLP_ENDPOINT    — Optional OTLP collector endpoint

Run:
    uv run --prerelease=allow \
        python/samples/02-agents/harness/build_your_own_claw/claw_step04_production_ready/console_app.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from agent_framework.observability import configure_otel_providers, get_tracer
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.trace.span import format_trace_id

_HARNESS_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_HARNESS_DIR))
from agent import build_claw_agent  # noqa: E402
from console import build_observers_with_planning, run_agent_async  # noqa: E402


async def main() -> None:
    """Run the production-ready claw in the local interactive console."""
    load_dotenv()
    # The agent factory reports its startup wiring (skills, Purview, shell, file access) through
    # ``logging``, so that it is visible on Foundry hosted agents, which surface only stderr.
    # Configure a handler here so those diagnostics also show up in the local console.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    configure_otel_providers()

    with get_tracer().start_as_current_span("Claw Console Session", kind=trace.SpanKind.CLIENT) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")
        agent = await build_claw_agent(credential=AzureCliCredential())
        async with agent:
            session = agent.create_session()

            await run_agent_async(
                agent,
                session=session,
                observers=build_observers_with_planning(agent),
                initial_mode="execute",
                title="💹 Finance Assistant",
                placeholder="Value a stock, score risk, research tickers, or tidy confirmations...",
            )


if __name__ == "__main__":
    asyncio.run(main())
