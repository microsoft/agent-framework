# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

# Uncomment this filter to suppress the experimental FileHistoryProvider warning
# before running the sample.
# import warnings  # isort: skip
# warnings.filterwarnings("ignore", message=r"\[FILE_HISTORY\].*", category=FutureWarning)
from agent_framework import Agent, FileHistoryProvider, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

try:
    import orjson  # pyright: ignore[reportMissingImports]
except ImportError:
    orjson = None


# Load environment variables from .env file.
load_dotenv()

"""
File History Provider

This sample demonstrates how to use the experimental `FileHistoryProvider` with
`FoundryChatClient` and a function tool so the persisted JSON Lines file shows
the tool-calling loop as well as the regular chat turns.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Azure AI Foundry project endpoint.
    FOUNDRY_MODEL: Foundry model deployment name.

Key components:
- `FileHistoryProvider`: Stores one message JSON object per line in a local
  `.jsonl` file for each session.
- `lookup_weather`: A function tool that makes the persisted file show the
  assistant function call and tool result lines.
- `json.dumps(..., indent=2)`: Pretty-prints selected records in the sample
  output while keeping the on-disk JSONL file compact and valid.
- `USE_TEMP_DIRECTORY`: Toggle between a temporary directory and a persistent
  `sessions/` folder next to this sample file.

Security posture:
- The history files are plaintext JSONL on disk, so use a trusted storage
  directory and treat the files as conversation logs, not as secure secret
  storage.
- Path safety checks protect the filename derived from the session id, but they
  do not redact message contents or encrypt the file.
"""

USE_TEMP_DIRECTORY = False
"""When True, store JSONL files in a temporary directory for this run only."""

LOCAL_SESSIONS_DIRECTORY_NAME = "sessions"
"""Folder name used when persisting history next to this sample file."""


@tool(approval_mode="never_require")
def lookup_weather(
    location: Annotated[str, Field(description="The city to look up weather for.")],
) -> str:
    """Return a deterministic weather report for a city."""
    weather_reports = {
        "Seattle": "Seattle is rainy with a high of 13C.",
        "Amsterdam": "Amsterdam is cloudy with a high of 16C.",
    }
    return weather_reports.get(location, f"{location} is sunny with a high of 20C.")


@contextmanager
def _resolve_storage_directory() -> Iterator[Path]:
    """Yield the configured storage directory for the sample run."""
    if USE_TEMP_DIRECTORY:
        with tempfile.TemporaryDirectory(prefix="af-file-history-") as temp_directory:
            yield Path(temp_directory)
        return

    storage_directory = Path(__file__).resolve().parent / LOCAL_SESSIONS_DIRECTORY_NAME
    storage_directory.mkdir(parents=True, exist_ok=True)
    yield storage_directory


async def main() -> None:
    """Run the file history provider sample."""

    with _resolve_storage_directory() as storage_directory:
        print(f"Using temporary directory: {USE_TEMP_DIRECTORY}")
        print(f"Storage directory: {storage_directory}\n")

        # 2. Create the agent with a tool so the JSONL file includes tool-calling messages.
        agent = Agent(
            client=FoundryChatClient(
                project_endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT"),
                model=os.getenv("FOUNDRY_MODEL"),
                credential=AzureCliCredential(),
            ),
            name="FileHistoryAgent",
            instructions=(
                "You are a helpful assistant, use the lookup_weather tool for weather questions and "
                "answer with the tool result in one sentence."
            ),
            tools=[lookup_weather],
            # if orjson is available, use it for faster JSON serialization in the FileHistoryProvider,
            # otherwise fall back to the default json module.
            context_providers=[
                FileHistoryProvider(
                    storage_directory,
                    dumps=orjson.dumps if orjson else None,
                    loads=orjson.loads if orjson else None,
                )
            ],
            default_options={"store": False},
        )

        # 3. Let Agent create the default UUID session id for this conversation.
        session = agent.create_session()

        # 4. Ask a question that triggers the weather tool.
        print("=== Run with tool calling ===")
        query = "Use the lookup_weather tool for Seattle and tell me the weather."
        response = await agent.run(query, session=session)
        print(f"User:      {query}")
        print(f"Assistant: {response.text}\n")

        # 5. Ask a follow-up question that triggers the weather tool as well
        print("=== Follow-up question ===")
        query = "And what about Amsterdam?"
        response = await agent.run(query, session=session)
        print(f"User:      {query}")
        print(f"Assistant: {response.text}\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Using temporary directory: False
Storage directory: /path/to/samples/02-agents/conversations/sessions

=== Run with tool calling ===
User:      Use the lookup_weather tool for Seattle and tell me the weather.
Assistant: <model response varies>
=== Follow-up question ===
User:      And what about Amsterdam?
Assistant: <model response varies>
"""
