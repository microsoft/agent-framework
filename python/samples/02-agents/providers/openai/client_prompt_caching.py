# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Content, Message
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions
from dotenv import load_dotenv

load_dotenv()

"""
OpenAI Chat Client Prompt Caching Example

Demonstrates explicit prompt cache breakpoints on GPT-5.6 and later models. Cache
writes are billed on these models, so marking exactly where a reusable prefix ends
lets you control what gets cached.

Two knobs work together:

- ``prompt_cache_options`` on ``OpenAIChatOptions`` sets the request-wide policy.
  ``{"mode": "explicit"}`` disables the automatic breakpoint on the latest message,
  so only the breakpoints you place are used for cache reads and writes.
- ``Content.additional_properties["prompt_cache_breakpoint"]`` marks the end of the
  reusable prefix on a specific content part.

The content before a breakpoint must be at least 1024 tokens long to be cached.
Running the same prefix twice shows the cache hit through
``usage_details["cache_read_input_token_count"]`` on later responses.

Environment variables:
    OPENAI_API_KEY — OpenAI API key

See: https://developers.openai.com/api/docs/guides/prompt-caching#prompt-cache-breakpoints
"""

# A stable block of context that is reused across requests, for example a product
# catalog, a policy document, or long system guidance. Repeated here to clear the
# 1024-token minimum a cache breakpoint requires.
STABLE_CONTEXT = (
    "You are a support assistant for the Contoso appliance store. "
    "Always answer briefly, quote the relevant catalog section, and never invent "
    "model numbers. If a question is out of scope, say so and point the customer "
    "to support@contoso.example. "
) * 40


def build_messages(question: str) -> list[Message]:
    """Build a request with a cache breakpoint at the end of the stable prefix."""
    return [
        Message(
            role="user",
            contents=[
                Content.from_text(
                    STABLE_CONTEXT,
                    additional_properties={"prompt_cache_breakpoint": {"mode": "explicit"}},
                )
            ],
        ),
        Message(role="user", contents=[Content.from_text(question)]),
    ]


async def main() -> None:
    print("\033[92m=== OpenAI Chat Client Prompt Caching Example ===\033[0m\n")

    client = OpenAIChatClient[OpenAIChatOptions](model="gpt-5.6-luna")
    options: OpenAIChatOptions = {"prompt_cache_options": {"mode": "explicit"}}

    questions = ["Do you sell refrigerators?", "What is the return policy contact?"]
    for turn, question in enumerate(questions, start=1):
        response = await client.get_response(build_messages(question), options=options)
        usage = response.usage_details or {}
        cached = usage.get("cache_read_input_token_count", 0)
        print(f"Turn {turn}: {question}")
        print(f"  Answer: {response.text}")
        print(f"  Cached input tokens: {cached}\n")
        if turn < len(questions):
            # A freshly written cache entry becomes readable shortly after the request
            # completes; the brief pause keeps the next turn from racing this one.
            await asyncio.sleep(2)

    print("The first turn writes the prefix to the cache; later turns read it back.")


if __name__ == "__main__":
    asyncio.run(main())
