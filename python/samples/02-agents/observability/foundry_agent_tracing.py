# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-foundry",
#     "azure-monitor-opentelemetry",
# ]
# ///
# Run from python/ with the workspace environment:
#   uv run python samples/02-agents/observability/foundry_agent_tracing.py

# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import argparse
import asyncio
import os

from agent_framework.foundry import FoundryAgent
from agent_framework.observability import create_resource, get_tracer
from azure.identity.aio import AzureCliCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

"""
Trace calls to an existing Foundry agent without coupling identity to exporter setup.

Default: the agent helper configures Azure Monitor and discovers the project's ARM ID.
With --manual-setup: configure the exporter yourself and pass project_arm_id to the agent.
Add --stream for streaming output. Message-content recording remains disabled.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT -- Foundry project endpoint.
    FOUNDRY_AGENT_NAME       -- Existing prompt or hosted agent name.
    FOUNDRY_AGENT_VERSION    -- Optional agent version.
    FOUNDRY_PROJECT_ARM_ID   -- Full project ARM ID; required for --manual-setup.
    APPLICATIONINSIGHTS_CONNECTION_STRING -- Required for --manual-setup; must target
        the Application Insights resource connected to the agent's Foundry project.

The sample reads FOUNDRY_PROJECT_ARM_ID explicitly; FoundryAgent does not automatically
read that environment variable. The ARM ID includes subscription, resource group,
account and project, and is different from the data-plane endpoint.

After running, open the existing agent in Foundry, select Traces, and search for the
printed trace ID. Look for the client invoke_agent and chat spans. The sample does not
create or delete the agent, so it remains available for inspection.
"""

load_dotenv()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Compare helper and application-managed Foundry tracing setup.")
    parser.add_argument("--manual-setup", action="store_true", help="Configure Azure Monitor outside the agent helper.")
    parser.add_argument("--stream", action="store_true", help="Stream the agent response.")
    args = parser.parse_args()
    project_arm_id = os.getenv("FOUNDRY_PROJECT_ARM_ID")
    if args.manual_setup and not project_arm_id:
        parser.error("--manual-setup requires FOUNDRY_PROJECT_ARM_ID.")

    # 1. Application-managed exporters are configured once, independently of agent identity.
    if args.manual_setup:
        configure_azure_monitor(
            connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"],
            resource=create_resource(),
        )

    async with (
        AzureCliCredential() as credential,
        FoundryAgent(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            project_arm_id=project_arm_id,
            agent_name=os.environ["FOUNDRY_AGENT_NAME"],
            agent_version=os.getenv("FOUNDRY_AGENT_VERSION"),
            credential=credential,
        ) as agent,
    ):
        # 2. Alternatively, discover attribution and configure Azure Monitor through the agent.
        # A supplied project_arm_id bypasses discovery in either setup.
        if not args.manual_setup:
            await agent.configure_azure_monitor()

        # 3. Group the client operation beneath an application span without project attributes.
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
