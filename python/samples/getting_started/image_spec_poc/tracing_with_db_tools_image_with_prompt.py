# Copyright (c) Microsoft. All rights reserved.

# The user passes the prompt + image_uri + text_id to the agent and requests for the image from the database.

import asyncio
import base64
import os
from typing import Annotated

import dotenv
from datetime import datetime, timezone
from agent_framework import ChatAgent, ChatMessage, DataContent, Role, TextContent
from agent_framework.observability import get_tracer
from agent_framework.azure import AzureAIClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import Field
from db_setup import SQLiteImageStore

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
    mime_type = record.mime_type or "application/octet-stream"
    base64_data = base64.b64encode(record.image_data).decode("utf-8")
    # truncate to keep tool payload small
    base64_data = base64_data[:256] + "...(truncated)" if len(base64_data) > 256 else base64_data
    return {
        "description": record.description or "",
        "image_uri": f"data:{mime_type};base64,{base64_data}",
        "query": {
            "sql": f"SELECT * FROM images WHERE text_id = {text_id}",
        },
    }

# Image encoded using base64
def create_sample_image() -> tuple[str, str]:
    """Load and encode the elephant image as base64."""
    with open("./elephant.jpg", "rb") as f:
        image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        image_uri = f"data:image/jpeg;base64,{image_base64}"
    return image_uri, image_base64



async def main() -> None:
    global store
    store = SQLiteImageStore()
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project,
        AzureAIClient(project_client=project, agent_name="ImageAnalyzerAgent") as client,
    ):
        await client.setup_azure_ai_observability(enable_sensitive_data=True)

        # Store encoded image in the database
        image_uri, image_base64 = create_sample_image()
        text_id = f"elephant-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        record = await store.add_image_from_base64(
            text_id=text_id,
            base64_data=image_base64,
            image_name="elephant.jpg",
            description="Sample elephant image",
            metadata={"source": "sample", "scenario": "azure_ai_chat_client"},
            tags=["elephant"],
            mime_type="image/jpeg",
        )
        print(f"Stored image in SQLite with id={record.id} text_id={record.text_id}")


        with get_tracer().start_as_current_span(
            name="Get Image from DB Tool", kind=SpanKind.CLIENT
        ) as current_span:
            print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

            agent = ChatAgent(
                chat_client=client,
                name="ImageFetchingAgent",
                tools=[get_image_data],
                instructions=(
                    "You must call the get_image_data tool using the text_id provided in the user's message before responding. "
                    "The tool returns a truncated image_uri; do not expand it."
                    "Do NOT wrap the JSON in Markdown, code fences, or additional narration."
                ),
            )

            # User passes the text_id of the image to be fetched from the database
            message = ChatMessage(
                role=Role.USER,
                contents=[
                    TextContent(
                        text=(
                            "Get me the image with the text_id=elephant.jpg-20260108T210722\n"
                                "Return plain text, one field per line, exactly:\n"
                                "description: <value>\n"
                                "image_uri: <value>\n"
                                "sql_query: <value>\n"
                                "No Markdown or extra text."
                        )
                    ),
                    DataContent(uri=image_uri, media_type="image/jpeg"),
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

