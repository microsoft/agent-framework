# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-ag-ui",
#     "agent-framework-foundry",
#     "azure-identity",
#     "azure-monitor-opentelemetry",
#     "fastapi",
#     "python-dotenv",
#     "uvicorn",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

"""AG-UI single-agent demo backend.

This sample exposes one Foundry-backed Agent over AG-UI and pairs it with the
React frontend in `../frontend`.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Microsoft Foundry project endpoint.
    FOUNDRY_MODEL: Model deployment name.
    ENABLE_AZURE_MONITOR: Set to true to export traces to the project's Application Insights resource.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from agent_framework import Agent
from agent_framework.ag_ui import (
    InMemoryAGUIThreadSnapshotStore,
    add_agent_framework_fastapi_endpoint,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logger = logging.getLogger(__name__)


# 1. Create one Foundry-backed agent with no tools or context providers.
def create_client() -> FoundryChatClient:
    """Create the Foundry chat client used by the sample."""

    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )


def create_agent(client: FoundryChatClient) -> Agent:
    """Create a single chat agent with no tools and no context providers."""

    return Agent(
        id="assistant",
        name="assistant",
        instructions="You are a helpful, concise assistant. Answer the user's questions directly.",
        client=client,
    )


# 2. Configure the AG-UI endpoint, thread history, and optional trace export.
def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    client = create_client()
    agent = create_agent(client)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if os.getenv("ENABLE_AZURE_MONITOR", "false").casefold() in {"1", "true", "yes", "on"}:
            await client.configure_azure_monitor()
            logger.info("Azure Monitor telemetry export is enabled")
        yield

    app = FastAPI(title="AG-UI Single Agent Demo", lifespan=lifespan)

    cors_origins = [
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173").split(",") if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    add_agent_framework_fastapi_endpoint(
        app=app,
        agent=agent,
        path="/agent",
        # Persist conversation history server-side, keyed by thread_id, so the
        # client only ever sends the newest message plus its thread_id.
        snapshot_store=InMemoryAGUIThreadSnapshotStore(),
        # AG-UI thread ids are not an authorization boundary, so a scope is required
        # when a snapshot store is configured. This demo is single-tenant, so every
        # request maps to one shared scope.
        snapshot_scope_resolver=lambda _request: "demo",
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


# 3. Run the backend for the React frontend.
async def main() -> None:
    """Run the AG-UI single-agent demo backend."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8892"))

    print(f"AG-UI single-agent demo backend running at http://{host}:{port}")
    print("AG-UI endpoint: POST /agent")

    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port))
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
AG-UI single-agent demo backend running at http://127.0.0.1:8892
AG-UI endpoint: POST /agent
"""
