# Copyright (c) Microsoft. All rights reserved.

import argparse
import os
import sys

import uvicorn
from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from agent_definitions import AGENT_CARD_FACTORIES, AGENT_FACTORIES
from agent_executor import AgentFrameworkExecutor
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
A2A Server Sample — Host an Agent Framework agent as an A2A endpoint

This sample creates a Python-based A2A-compliant server that wraps an Agent
Framework agent.  The server uses the a2a-sdk's Starlette application to handle
JSON-RPC requests and serves the AgentCard at /.well-known/agent.json.

Three agent types are available:
  - invoice   — Answers invoice queries using mock data and function tools.
  - policy    — Returns a fixed policy response.
  - logistics — Returns a fixed logistics response.

Usage:
  uv run python a2a_server.py --agent-type policy --port 5001
  uv run python a2a_server.py --agent-type invoice --port 5000
  uv run python a2a_server.py --agent-type logistics --port 5002

Environment variables:
  AZURE_AI_PROJECT_ENDPOINT              — Your Azure AI Foundry project endpoint
  AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME — Model deployment name (e.g. gpt-4o)
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A2A Agent Server")
    parser.add_argument(
        "--agent-type",
        choices=["invoice", "policy", "logistics"],
        default="policy",
        help="Type of agent to host (default: policy)",
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host to bind to (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5001,
        help="Port to listen on (default: 5001)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Validate environment
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    deployment_name = os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME")

    if not project_endpoint:
        print("Error: AZURE_AI_PROJECT_ENDPOINT environment variable is not set.")
        sys.exit(1)
    if not deployment_name:
        print("Error: AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME environment variable is not set.")
        sys.exit(1)

    # Create the LLM client
    credential = AzureCliCredential()
    client = AzureOpenAIResponsesClient(
        project_endpoint=project_endpoint,
        deployment_name=deployment_name,
        credential=credential,
    )

    # Create the Agent Framework agent for the chosen type
    agent_factory = AGENT_FACTORIES[args.agent_type]
    agent = agent_factory(client)

    # Build the A2A server components
    url = f"http://{args.host}:{args.port}/"
    agent_card = AGENT_CARD_FACTORIES[args.agent_type](url)
    executor = AgentFrameworkExecutor(agent)
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
    )

    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    print(f"Starting A2A server: {agent_card.name}")
    print(f"  Agent type : {args.agent_type}")
    print(f"  Listening  : {url}")
    print(f"  Agent card : {url}.well-known/agent.json")
    print()

    uvicorn.run(
        a2a_app.build(),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
