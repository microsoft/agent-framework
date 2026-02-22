# Copyright (c) Microsoft. All rights reserved.

# Scenario where the DB has a bunch of images stored and the user provides text_id to fetch the image.

import asyncio
import base64
import os
from typing import Annotated

import dotenv
from agent_framework import ChatAgent, ChatMessage, Role, TextContent
from agent_framework.observability import get_tracer, enable_instrumentation
from agent_framework.azure import AzureAIClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import Field
from db_setup import SQLiteImageStore
from db_storing_logic import create_and_store_base64_encoded_images

dotenv.load_dotenv()

store: SQLiteImageStore | None = None

async def get_image_data(
    text_id: Annotated[
        str,
        Field(description="Fetch stored image metadata, image URI for a given text_id."),
    ],
) -> dict[str, object]:
    if store is None:
        raise RuntimeError("Image store is not initialized")
    record = await store.get_image_by_text_id(text_id=text_id, include_data=True)
    if record is None or record.image_data is None:
        raise ValueError(f"No image stored for text_id={text_id}")
    # Prefer the stored image_uri from metadata; fall back to image_path
    image_uri = None
    if isinstance(record.metadata, dict):
        image_uri = record.metadata.get("image_uri")
    if not image_uri:
        image_uri = record.image_path or ""
    # truncate to keep tool payload small
    image_uri = image_uri[:256] + "...(truncated)" if len(image_uri) > 256 else image_uri
    return {
        "description": record.description or "",
        "image_uri": image_uri,
        "query": {
            "sql": f"SELECT * FROM images WHERE text_id = {text_id}",
        },
    }

async def main() -> None:
    """Run image analysis with Azure OpenAI and collect telemetry."""
    global store
    store = SQLiteImageStore()
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project,
        AzureAIClient(project_client=project) as client,
    ):
        await client.configure_azure_monitor()

        enable_instrumentation(enable_sensitive_data=True)

        await create_and_store_base64_encoded_images()

        with get_tracer().start_as_current_span(
            name="Get Image Data using text_id", kind=SpanKind.CLIENT
        ) as current_span:
            print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

            agent = ChatAgent(
                chat_client=client,
                name="ImageInspector",
                tools=[get_image_data],
                instructions=(
                    "You must call the get_image_data tool using the text_id provided in the user's message before responding. "
                    "The tool returns a truncated image_uri; do not expand it. "
                    "After you receive the tool response, output JSON that copies the tool fields exactly (description, image_uri, query). "
                    "The query field must remain an object with keys sql. Do not convert it to text. "
                    "Do NOT wrap the JSON in Markdown, code fences, or additional narration."
                ),
            )

            message = ChatMessage(
                role=Role.USER,
                contents=[
                    TextContent(
                            text=(
                                "Get me the image with the text_id=cat.jpg-20260109T195203\n"
                                "Return plain text, one field per line, exactly:\n"
                                "description: <value>\n"
                                "image_uri: <value>\n"
                                "sql_query: <value>\n"
                                "No Markdown or extra text."
                            )
                    ),
                ],
            )

            async with agent:
                thread = agent.get_new_thread()
                response = await agent.run(message, thread=thread, store=True)

            if response.messages:
                assistant_reply = response.messages[-1]
                print("Assistant response:")
                for content in assistant_reply.contents:
                    print(content)


if __name__ == "__main__":
    asyncio.run(main())
