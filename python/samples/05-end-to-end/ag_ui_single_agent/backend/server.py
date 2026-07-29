# Copyright (c) Microsoft. All rights reserved.

"""AG-UI single-agent demo backend.

This is the simplest possible AG-UI integration: a single chat agent with no
tools and no context providers, exposed over the AG-UI protocol.

Run this server and pair it with the frontend in `../frontend`.
"""

from __future__ import annotations

import logging
import os

import uvicorn
from agent_framework import Agent
from agent_framework.ag_ui import (
    InMemoryAGUIThreadSnapshotStore,
    add_agent_framework_fastapi_endpoint,
)
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logger = logging.getLogger(__name__)


def create_agent() -> Agent:
    """Create a single chat agent with no tools and no context providers."""

    from agent_framework.foundry import FoundryChatClient
    from azure.identity import AzureCliCredential

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    return Agent(
        id="assistant",
        name="assistant",
        instructions="You are a helpful, concise assistant. Answer the user's questions directly.",
        client=client,
    )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(title="AG-UI Single Agent Demo")

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
        agent=create_agent(),
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


def main() -> None:
    """Run the AG-UI single-agent demo backend."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8892"))

    print(f"AG-UI single-agent demo backend running at http://{host}:{port}")
    print("AG-UI endpoint: POST /agent")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
