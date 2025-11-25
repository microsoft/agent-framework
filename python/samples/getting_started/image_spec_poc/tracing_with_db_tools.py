# Copyright (c) Microsoft. All rights reserved.


import asyncio
import base64
import os
from typing import Annotated

import dotenv
from datetime import datetime, timezone
from agent_framework import ChatAgent, ChatMessage, DataContent, Role, TextContent
from agent_framework.observability import get_tracer
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import Field
from db_setup import SQLiteImageStore


"""
This sample, shows you can leverage the built-in telemetry in Azure AI.
It uses the Azure AI client to setup the telemetry, this calls out to
Azure AI for the connection string of the attached Application Insights
instance.

You must add an Application Insights instance to your Azure AI project
for this sample to work.
"""

# For loading the `AZURE_AI_PROJECT_ENDPOINT` environment variable
dotenv.load_dotenv()

store: SQLiteImageStore | None = None

async def get_image_data(
    text_id: Annotated[
        str,
        Field(description="Fetch stored image metadata, data URI, and exported file URI for a given text_id."),
    ],
) -> dict[str, object]:
    if store is None:
        raise RuntimeError("Image store is not initialized")
    record = await store.get_image_by_text_id(text_id=text_id, include_data=True)
    if record is None or record.image_data is None:
        raise ValueError(f"No image stored for text_id={text_id}")
    mime_type = record.mime_type or "application/octet-stream"
    base64_data = base64.b64encode(record.image_data).decode("utf-8")
    saved_path = await store.save_image_to_file(text_id=text_id)
    file_uri = saved_path.as_uri() if saved_path else ""
    return {
        "description": record.description or "",
        "image_uri": f"data:{mime_type};base64,{base64_data}",
        "file_uri": file_uri,
        "query": {
            "sql": "SELECT * FROM images WHERE text_id = ?",
            "parameters": {"text_id": text_id},
        },
    }

# Image analysis function replacing get_weather
def create_sample_image() -> tuple[str, str]:
    """Load and encode the elephant image as base64."""
    with open("../multimodal_input/elephant.jpg", "rb") as f:
        image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        image_uri = f"data:image/jpeg;base64,{image_base64}"
    return image_uri, image_base64



async def main() -> None:
    """Run image analysis with Azure OpenAI and collect telemetry."""
    global store
    store = SQLiteImageStore()
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project,
        AzureAIAgentClient(project_client=project) as client,
    ):
        await client.setup_azure_ai_observability(enable_sensitive_data=True)

        image_uri, image_base64 = create_sample_image()
        text_id = f"elephant-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        record = await store.add_image_from_base64(
            text_id=text_id,
            base64_data=image_base64,
            image_name="elephant.jpg",
            description="Sample elephant image used by the observability demo",
            metadata={"source": "sample", "scenario": "azure_ai_chat_client"},
            tags=["observability", "sample", "elephant"],
            mime_type="image/jpeg",
        )
        print(f"Stored image in SQLite with id={record.id} text_id={record.text_id}")

        with get_tracer().start_as_current_span(
            name="Get Image Data with Tool", kind=SpanKind.CLIENT
        ) as current_span:
            print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

            agent = ChatAgent(
                chat_client=client,
                name="ImageInspector",
                tools=[get_image_data],
                instructions=(
                    "You must call the get_image_data tool using the text_id provided in the user's message before responding. "
                    "After you receive the tool response, output JSON that copies the tool fields exactly (description, image_uri, file_uri, query). "
                    "The query field must remain an object with keys sql and parameters. Do not convert it to text. "
                    "Do NOT wrap the JSON in Markdown, code fences, or additional narration."
                ),
            )

            message = ChatMessage(
                role=Role.USER,
                contents=[
                    TextContent(
                        text=(
                            f"Use text_id={text_id} when calling the tool.\n"
                            "After invoking the tool, respond with JSON that mirrors the tool output exactly, including the query object.\n"
                            "Return exactly this schema: {\"description\": string, \"image_uri\": string, \"file_uri\": string, \"query\": {\"sql\": string, \"parameters\": {\"text_id\": string}}}.\n"
                            "Do not wrap the JSON in fences or add any additional text."
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

        updated_record = await store.add_tags(text_id=text_id, tags=["described"], replace_existing=False)
        if updated_record is not None:
            print(f"Updated tags for text_id={text_id}: {updated_record.tags()}")

        if (saved_path := await store.save_image_to_file(text_id=text_id)) is not None:
            print(f"Exported image to {saved_path}")


if __name__ == "__main__":
    asyncio.run(main())
