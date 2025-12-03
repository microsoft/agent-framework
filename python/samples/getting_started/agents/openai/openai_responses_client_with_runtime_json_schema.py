# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json

from agent_framework.openai import OpenAIResponsesClient

"""
OpenAI Chat Client Runtime JSON Schema Example

Demonstrates structured outputs when the schema is only known at runtime.
Uses additional_chat_options to pass a JSON Schema payload directly to OpenAI
without defining a Pydantic model up front.
"""


runtime_schema = {
    "title": "WeatherDigest",
    "type": "object",
    "properties": {
        "location": {"type": "string"},
        "conditions": {"type": "string"},
        "temperature_c": {"type": "number"},
        "advisory": {"type": "string"},
    },
    # OpenAI strict mode requires every property to appear in required.
    "required": ["location", "conditions", "temperature_c", "advisory"],
    "additionalProperties": False,
}


async def non_streaming_example() -> None:
    print("=== Non-streaming runtime JSON schema example ===")

    agent = OpenAIResponsesClient().create_agent(
        name="RuntimeSchemaAgent",
        instructions="Return only JSON that matches the provided schema. Do not add commentary.",
    )

    query = "Give a brief weather digest for Seattle."
    print(f"User: {query}")

    response = await agent.run(
        query,
        additional_chat_options={
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": runtime_schema["title"],
                    "strict": True,
                    "schema": runtime_schema,
                },
            },
        },
    )

    print("Model output:")
    print(response.text)

    parsed = json.loads(response.text)
    print("Parsed dict:")
    print(parsed)


async def streaming_example() -> None:
    print("=== Streaming runtime JSON schema example ===")

    agent = OpenAIResponsesClient().create_agent(
        name="RuntimeSchemaAgent",
        instructions="Return only JSON that matches the provided schema. Do not add commentary.",
    )

    query = "Give a brief weather digest for Portland."
    print(f"User: {query}")

    chunks: list[str] = []
    async for chunk in agent.run_stream(
        query,
        additional_chat_options={
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": runtime_schema["title"],
                    "strict": True,
                    "schema": runtime_schema,
                },
            },
        },
    ):
        if chunk.text:
            chunks.append(chunk.text)

    raw_text = "".join(chunks)
    print("Model output:")
    print(raw_text)

    parsed = json.loads(raw_text)
    print("Parsed dict:")
    print(parsed)


async def main() -> None:
    print("=== OpenAI Chat Client with runtime JSON Schema ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
