# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "agent-framework-ag-ui",
#     "agent-framework-openai",
#     "fastapi",
#     "python-dotenv",
#     "uvicorn",
# ]
# ///

# Copyright (c) Microsoft. All rights reserved.

"""Microsoft Agent Framework and OpenUI end-to-end sample backend.

The Agent Framework agent owns model calls, tools, approval pauses, streaming,
and thread history. Its assistant output is OpenUI Lang generated from the exact
component library rendered by the React frontend.

Environment variables:
    OPENAI_API_KEY: OpenAI API key used only by this backend.
    OPENAI_MODEL: Optional model name. Defaults to ``gpt-5.4-nano``.
    CORS_ORIGINS: Optional comma-separated browser origins.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import uvicorn
from agent_framework import Agent, tool
from agent_framework.ag_ui import InMemoryAGUIThreadSnapshotStore, add_agent_framework_fastapi_endpoint
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logger = logging.getLogger(__name__)

GENERATED_PROMPT_PATH = Path(__file__).parent / "generated" / "system-prompt.txt"


# 1. Define deterministic tools, including a tool that requires human approval.
@tool(approval_mode="never_require")
def get_quarterly_revenue() -> dict[str, list[str] | list[int]]:
    """Return synthetic quarterly revenue in thousands of dollars for a chart."""

    return {
        "quarters": ["Q1", "Q2", "Q3", "Q4"],
        "revenue_thousands": [120, 180, 150, 240],
    }


@tool(approval_mode="always_require")
def publish_revenue_report(
    title: str,
    audience: str,
    q1_revenue: int,
    q2_revenue: int,
    q3_revenue: int,
    q4_revenue: int,
) -> dict[str, object]:
    """Publish a synthetic report with quarterly revenue in thousands after approval."""

    quarterly_revenue = {
        "Q1": q1_revenue,
        "Q2": q2_revenue,
        "Q3": q3_revenue,
        "Q4": q4_revenue,
    }
    return {
        "status": "published",
        "title": title,
        "audience": audience,
        "quarterly_revenue_thousands": quarterly_revenue,
        "total_revenue_thousands": sum(quarterly_revenue.values()),
    }


# 2. Load the prompt generated from the frontend's exact OpenUI library.
def load_openui_prompt() -> str:
    """Load the generated OpenUI system prompt or explain how to create it."""

    if not GENERATED_PROMPT_PATH.is_file():
        raise RuntimeError(
            "OpenUI prompt is missing. Run `npm install` and `npm run generate:openui` "
            "from the sample's frontend directory."
        )
    return GENERATED_PROMPT_PATH.read_text(encoding="utf-8")


def create_client() -> OpenAIChatClient:
    """Create the Agent Framework OpenAI client used by the sample."""

    return OpenAIChatClient(
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.getenv("OPENAI_MODEL", "gpt-5.4-nano"),
    )


def create_agent(client: OpenAIChatClient) -> Agent:
    """Create the tool-using agent that produces OpenUI Lang responses."""

    responsibilities = """
## Agent Framework responsibilities

- Use `get_quarterly_revenue` when the user asks for the sample revenue data or asks you to fetch data for a chart.
- Use values supplied by the user directly when they provide their own complete dataset.
- Call `publish_revenue_report` only when the user explicitly asks to publish a report. It pauses for reviewer approval.
- Before calling `publish_revenue_report`, use complete Q1-Q4 values supplied by the user or call `get_quarterly_revenue`, then pass those exact values into the publishing tool.
- After a form action, read the submitted values from the user message context and acknowledge them in the next UI.
- Do not claim an approval-gated tool ran before its result is available.
"""

    return Agent(
        id="openui_assistant",
        name="OpenUI Assistant",
        description="Streams Agent Framework responses as rendered OpenUI components.",
        instructions=f"{load_openui_prompt()}\n{responsibilities}",
        client=client,
        tools=[get_quarterly_revenue, publish_revenue_report],
    )


# 3. Expose the agent through Agent Framework's AG-UI FastAPI endpoint.
def create_app() -> FastAPI:
    """Create the FastAPI application and its AG-UI endpoint."""

    app = FastAPI(title="Microsoft Agent Framework + OpenUI")
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

    agent = create_agent(create_client())
    add_agent_framework_fastapi_endpoint(
        app=app,
        agent=agent,
        path="/agent",
        snapshot_store=InMemoryAGUIThreadSnapshotStore(),
        # This sample is intentionally single-tenant. Production apps must map
        # authenticated users to isolated scopes instead of sharing "demo".
        snapshot_scope_resolver=lambda _request: "demo",
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


# 4. Run the backend locally for the Vite frontend.
async def main() -> None:
    """Run the Agent Framework and OpenUI sample backend."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8894"))

    print(f"Microsoft Agent Framework + OpenUI backend running at http://{host}:{port}")
    print("AG-UI endpoint: POST /agent")

    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port))
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
Microsoft Agent Framework + OpenUI backend running at http://127.0.0.1:8894
AG-UI endpoint: POST /agent
"""
