# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa: T201

from __future__ import annotations

import asyncio
import json
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
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

try:
    import orjson
except ImportError:
    orjson = None


load_dotenv()

"""
File History Provider Conversation Persistence

This sample demonstrates persisting a tool-driven conversation with the
experimental `FileHistoryProvider`, reading the stored JSONL file back from
disk, and then continuing the same conversation with another city.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Azure AI Foundry project endpoint.
    FOUNDRY_MODEL: Foundry model deployment name.

Key components:
- `FileHistoryProvider`: Stores one message JSON object per line in a local
  `.jsonl` file for each session.
- `get_weather`: A function tool that makes the persisted file show the
  assistant function call and tool result records.
- `json.dumps(..., indent=2)`: Pretty-prints a few persisted JSONL records
  while keeping the on-disk file compact and valid.
- `load_dotenv()`: Loads `.env` values up front so the sample can stay focused
  on history persistence instead of manual environment variable plumbing.
- Optional `orjson`: Uses `orjson.dumps` / `orjson.loads` automatically when
  available, otherwise falls back to the standard library `json` module.

Security posture:
- The history file is plaintext JSONL on disk, so use a trusted storage
  directory and treat it as conversation logging, not as secure secret storage.
- Path safety checks protect the filename derived from the session id, but they
  do not redact message contents or encrypt the file.
"""

USE_TEMP_DIRECTORY = False
"""When True, store JSONL files in a temporary directory for this run only."""

LOCAL_SESSIONS_DIRECTORY_NAME = "sessions"
"""Folder name used when persisting history next to this sample file."""


@tool(approval_mode="never_require")
def get_weather(
    city: Annotated[str, Field(description="The city to get the weather for.")],
) -> str:
    """Return a deterministic weather report for a city."""
    weather_reports = {
        "Seattle": "Seattle is rainy with a high of 13C.",
        "Amsterdam": "Amsterdam is cloudy with a high of 16C.",
    }
    return weather_reports.get(city, f"{city} is sunny with a high of 20C.")


@contextmanager
def _resolve_storage_directory() -> Iterator[Path]:
    """Yield the configured storage directory for the sample run."""
    if USE_TEMP_DIRECTORY:
        with tempfile.TemporaryDirectory(prefix="af-file-history-resume-") as temp_directory:
            yield Path(temp_directory)
        return

    storage_directory = Path(__file__).resolve().parent / LOCAL_SESSIONS_DIRECTORY_NAME
    storage_directory.mkdir(parents=True, exist_ok=True)
    yield storage_directory


async def main() -> None:
    """Run the file history provider conversation persistence sample."""

    with _resolve_storage_directory() as storage_directory:
        print(f"Using temporary directory: {USE_TEMP_DIRECTORY}")
        print(f"Storage directory: {storage_directory}\n")

        # 1. Create the client, history provider, and tool-enabled agent.
        agent = Agent(
            client=FoundryChatClient(
                credential=AzureCliCredential(),
            ),
            name="WeatherHistoryAgent",
            instructions=(
                "You are a helpful assistant. Use the get_weather tool for weather questions "
                "and answer in one sentence using the tool result."
            ),
            tools=[get_weather],
            context_providers=[
                FileHistoryProvider(
                    storage_directory,
                    dumps=orjson.dumps if orjson else None,
                    loads=orjson.loads if orjson else None,
                )
            ],
            default_options={"store": False},
        )

        # 2. Ask about the first city so the JSONL file is created on disk.
        session = agent.create_session()
        history_file = storage_directory / f"{session.session_id}.jsonl"
        print("=== First weather question ===\n")
        first_query = "Use the get_weather tool and tell me the weather in Seattle."
        first_response = await agent.run(first_query, session=session)
        print(f"User:      {first_query}")
        print(f"Assistant: {first_response.text}\n")

        # 3. Read the stored JSONL records back from disk and pretty-print a few of them.
        raw_lines = (await asyncio.to_thread(history_file.read_text, encoding="utf-8")).splitlines()
        print(f"Stored message lines after first question: {len(raw_lines)}")
        print(f"History file: {history_file}\n")
        print("=== JSONL preview from disk ===\n")
        for index, line in enumerate(raw_lines[:4], start=1):
            print(f"Record {index}:")
            print(json.dumps(json.loads(line), indent=2))
            print()

        # 4. Continue the same persisted conversation with another city.
        print("=== Second weather question ===\n")
        second_query = "Now use the get_weather tool for Amsterdam."
        second_response = await agent.run(second_query, session=session)
        print(f"User:      {second_query}")
        print(f"Assistant: {second_response.text}\n")

        updated_lines = (await asyncio.to_thread(history_file.read_text, encoding="utf-8")).splitlines()
        print(f"Stored message lines after second question: {len(updated_lines)}")
        print(f"History file: {history_file}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
Using temporary directory: False
Storage directory: /path/to/samples/02-agents/conversations/sessions

=== First weather question ===

User:      Use the get_weather tool and tell me the weather in Seattle.
Assistant: <model response varies>

Stored message lines after first question: 4
History file: /path/to/samples/02-agents/conversations/sessions/<session-uuid>.jsonl

=== JSONL preview from disk ===

Record 1:
{
  "type": "message",
  "role": "user",
  ...
}

=== Second weather question ===

User:      Now use the get_weather tool for Amsterdam.
Assistant: <model response varies>

Stored message lines after second question: 8
History file: /path/to/samples/02-agents/conversations/sessions/<session-uuid>.jsonl
"""
