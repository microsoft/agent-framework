# Copyright (c) Microsoft. All rights reserved.
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "agent-framework-azure-cosmos-memory",
#     "agent-framework-foundry",
#     "python-dotenv",
# ]
# ///

"""Interactive chat with a CUSTOM memory-extraction rubric.

This is a second flavor of ``interactive_chat.py`` that shows how to control *what* the
memory pipeline extracts by supplying a custom extraction prompt. The Agent Memory Toolkit
drives fact/episodic extraction with a Prompty template (``extract_memories.prompty``); the
provider's ``prompts_dir`` parameter points the pipeline at a directory of templates you own,
so you can tune the classification rules for your domain.

The toolkit's default rubric is domain-agnostic and tends to classify project-scoped technical
decisions as *episodic* memories. For a coding assistant you usually want architectural
decisions (patterns, library choices, error-handling strategy) to persist as durable *facts*.
This sample augments the bundled prompt with exactly that guidance.

Because the pipeline loads every template by name from ``prompts_dir`` (with no fallback to the
bundled copies), the sample builds a complete prompts directory at startup: it copies the
toolkit's bundled templates and overlays an augmented ``extract_memories.prompty``. Deriving
from the installed prompt keeps the output schema in sync with whatever toolkit version is
installed, instead of forking a 600-line template.

Set these environment variables (or put them in a ``.env`` file) before running:
    COSMOS_ENDPOINT     Azure Cosmos DB account endpoint
    FOUNDRY_ENDPOINT    Azure AI Foundry project endpoint (chat + embeddings)

Optional:
    COSMOS_DATABASE     Database name (default: ai_memory)
    CHAT_MODEL          Chat deployment (default: gpt-4o-mini)
    EMBEDDING_MODEL     Embedding deployment (default: text-embedding-3-large)

Run:
    python samples/interactive_chat_custom_extraction.py
"""

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

from agent_framework import Agent, AgentSession
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

from agent_framework_azure_cosmos_memory import CosmosMemoryContextProvider

# The extra guidance we inject into the extraction system prompt. This is the whole point of
# the sample: a small, readable rubric that changes how the LLM classifies what it reads.
CUSTOM_RUBRIC = """
## Coding-Assistant Extraction Rubric (custom override)

You are extracting memories for a software-engineering assistant. Apply these rules IN ADDITION
to everything above; when they conflict with the general guidance, THESE WIN:

- Treat technical and architectural decisions as durable **facts** (category: `decision`), even
  when they are made within a single project. Examples: chosen design patterns, library or
  framework choices, error-handling strategy, API/versioning conventions, data-access patterns.
  These are standing knowledge future sessions should recall, not one-off episodes.
- Capture coding **preferences and conventions** as facts (category: `preference` or
  `requirement`): style rules, testing expectations, "always/never" directives.
- Reserve **episodic** memories for concrete debugging or investigation experiences with a
  situation -> action -> outcome arc (e.g. "the build failed with X, we tried Y, Z fixed it").
"""


def _build_custom_prompts_dir() -> str:
    """Create a complete prompts directory with an augmented ``extract_memories.prompty``.

    Copies the toolkit's bundled templates into a fresh directory, then rewrites the extraction
    template's system prompt to include ``CUSTOM_RUBRIC``. Returns the new directory path.
    """
    import azure.cosmos.agent_memory as toolkit

    bundled = Path(toolkit.__file__).parent / "prompts"
    if not bundled.is_dir():  # pragma: no cover - defensive
        raise RuntimeError(f"Bundled prompts directory not found at {bundled}")

    work_dir = Path(tempfile.mkdtemp(prefix="af_custom_prompts_"))
    for template in bundled.glob("*.prompty"):
        shutil.copy2(template, work_dir / template.name)

    extract = work_dir / "extract_memories.prompty"
    text = extract.read_text(encoding="utf-8")
    # Insert the custom rubric immediately after the ``system:`` marker so it sits at the top of
    # the system prompt. The template format is: YAML front-matter, then a ``system:`` section.
    marker = "\nsystem:\n"
    idx = text.find(marker)
    if idx == -1:  # pragma: no cover - defensive; format changed upstream
        raise RuntimeError("Could not locate the 'system:' section in extract_memories.prompty")
    insert_at = idx + len(marker)
    extract.write_text(text[:insert_at] + CUSTOM_RUBRIC + "\n" + text[insert_at:], encoding="utf-8")
    return str(work_dir)


def create_agent_with_memory(prompts_dir: str) -> tuple[Agent, CosmosMemoryContextProvider]:
    """Create an agent wired to Cosmos DB memory that uses the custom extraction prompt."""
    cosmos_endpoint = os.environ.get("COSMOS_ENDPOINT")
    foundry_endpoint = os.environ.get("FOUNDRY_ENDPOINT")
    if not cosmos_endpoint or not foundry_endpoint:
        print("ERROR: set COSMOS_ENDPOINT and FOUNDRY_ENDPOINT (see this file's docstring).")
        sys.exit(1)

    credential = DefaultAzureCredential()
    provider = CosmosMemoryContextProvider(
        cosmos_endpoint=cosmos_endpoint,
        cosmos_database=os.getenv("COSMOS_DATABASE", "ai_memory"),
        foundry_endpoint=foundry_endpoint,
        credential=credential,
        top_k=5,
        min_confidence=0.7,
        memory_types=["fact", "procedural", "episodic"],
        context_prompt="## What I Remember About You\nI'll use these memories to personalize my responses:",
        # The one line that matters: point the extraction pipeline at our custom templates.
        prompts_dir=prompts_dir,
    )
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=foundry_endpoint,
            model=os.getenv("CHAT_MODEL", "gpt-4o-mini"),
            credential=credential,
        ),
        name="Coding Memory Assistant",
        instructions=(
            "You are a helpful software-engineering assistant with long-term memory. "
            "When you remember decisions or preferences, mention them naturally. "
            "If you don't remember something, say so instead of guessing."
        ),
        context_providers=[provider],
    )
    return agent, provider


def _new_session(agent: Agent, provider: CosmosMemoryContextProvider, user_id: str) -> AgentSession:
    """Start a fresh session (a new thread) scoped to the given user id."""
    session = agent.create_session()
    session.state.setdefault(provider.source_id, {})["user_id"] = user_id
    return session


async def chat_loop(agent: Agent, provider: CosmosMemoryContextProvider, user_id: str) -> None:
    """Run the interactive chat loop."""
    print("\n" + "=" * 70)
    print("  Interactive Chat with a CUSTOM extraction rubric")
    print("=" * 70)
    print(f"\nUser ID: {user_id}")
    print("\nCommands:  /new (new thread)   /user (switch user)   /quit")
    print("Tip: state an architectural decision, then /new and ask about it - it should be")
    print("recalled as a durable fact thanks to the custom rubric.\n")

    session = _new_session(agent, provider, user_id)
    print(f"Started thread: {session.session_id}\n")

    while True:
        # Read input in a worker thread so the asyncio event loop stays free while you type.
        # The provider extracts memories in a background task after each turn; a blocking
        # input() call would freeze the loop and defer all extraction until the app exits.
        user_input = (await asyncio.to_thread(input, "You: ")).strip()
        if not user_input:
            continue
        if user_input == "/quit":
            print("\nGoodbye!")
            break
        if user_input == "/new":
            session = _new_session(agent, provider, user_id)
            print(f"\n[New thread: {session.session_id} - earlier memories still available]\n")
            continue
        if user_input == "/user":
            new_user_id = (await asyncio.to_thread(input, "Enter new user ID: ")).strip()
            if new_user_id:
                user_id = new_user_id
                session = _new_session(agent, provider, user_id)
                print(f"\n[Switched to user {user_id}; new thread {session.session_id}]\n")
            continue

        response = await agent.run(user_input, session=session)
        print(f"\nAssistant: {response.text}\n")


async def main() -> None:
    """Entry point."""
    load_dotenv()
    prompts_dir = _build_custom_prompts_dir()
    print(f"Using custom extraction prompts from: {prompts_dir}")
    agent, provider = create_agent_with_memory(prompts_dir)
    # Memory extraction runs in the background after each turn; the provider drains any
    # in-flight extraction automatically when this ``async with`` block exits.
    try:
        async with provider:
            await chat_loop(agent, provider, user_id="demo-user-123")
    finally:
        shutil.rmtree(prompts_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
