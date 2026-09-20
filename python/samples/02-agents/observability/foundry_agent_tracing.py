# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-foundry",
#     "azure-monitor-opentelemetry>=1.8.10,<2",
# ]
# ///
# Run from python/ with the workspace environment:
#   uv run --group test python samples/02-agents/observability/foundry_agent_tracing.py

# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import argparse
import asyncio
import os

from agent_framework.foundry import FoundryAgent
from agent_framework.observability import get_tracer
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

"""
Trace calls to an existing Foundry agent, including the client and service spans.

Azure Monitor 1.8.10 or later instruments HTTPX and HTTPX2, which the OpenAI SDK
uses to send requests. The resulting traceparent header connects client spans
to Foundry's service spans. Older Azure Monitor versions can export the client
spans to Application Insights while leaving them in a separate trace.

The helper configures Azure Monitor using the project's connected Application
Insights resource. No project ARM ID or custom span attributes are needed.
Add --stream for streaming output. Message-content recording remains disabled.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT -- Foundry project endpoint.
    FOUNDRY_AGENT_NAME       -- Existing prompt or hosted agent name.
    FOUNDRY_AGENT_VERSION    -- Required for PromptAgents; optional for HostedAgents.

After running, open Build > Agents > your agent > Traces in Foundry. Select the
agent version and a time range covering the run, then open the printed trace ID.
The waterfall should contain this application's parent span, client invoke_agent
and chat spans, the HTTP request, and the service spans in one connected tree.
The sample does not create or delete the agent, so it remains available for inspection.
"""

load_dotenv()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Trace client and service calls to an existing Foundry agent.")
    parser.add_argument("--stream", action="store_true", help="Stream the agent response.")
    args = parser.parse_args()

    # 1. Connect to an existing agent without changing its definition.
    async with (
        AzureCliCredential() as credential,
        FoundryAgent(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            agent_name=os.environ["FOUNDRY_AGENT_NAME"],
            agent_version=os.getenv("FOUNDRY_AGENT_VERSION"),
            credential=credential,
        ) as agent,
    ):
        # 2. Configure export and HTTP trace-context propagation before invoking the agent.
        await agent.configure_azure_monitor(enable_live_metrics=False)

        # 3. Group the client operation beneath an application span.
        with get_tracer().start_as_current_span("foundry-agent-tracing") as span:
            print(f"Trace ID: {span.get_span_context().trace_id:032x}")
            if args.stream:
                result_stream = agent.run("Say hello in one sentence.", stream=True)
                async for update in result_stream:
                    if update.text:
                        print(update.text, end="", flush=True)
                print()
                response = await result_stream.get_final_response()
            else:
                response = await agent.run("Say hello in one sentence.")
                print(response.text)
            print(f"Agent response ID: {response.response_id}")

    # 4. Flush before exit; exporting does not by itself prove Foundry portal discovery.
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider) and not provider.force_flush():
        raise TimeoutError("Trace export did not finish before the flush timeout.")


if __name__ == "__main__":
    asyncio.run(main())

# Example output:
# Trace ID: <trace ID to search for in Foundry>
# Hello! How can I help you today?
# Agent response ID: <service response ID>
