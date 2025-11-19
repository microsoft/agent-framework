# Copyright (c) Microsoft. All rights reserved.


import asyncio
import base64
import json
import os
from typing import Any, Annotated

import dotenv
from agent_framework import ChatMessage, DataContent, Role, TextContent, ChatAgent
from agent_framework.observability import get_tracer
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import Field


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

async def get_image_data(
    location: Annotated[str, Field(description="Get image by textid")],
) -> str:
    textid = "elephant-20251030T233148"
    return f"The image corresponding to {textid} is image_uri: 1234 and the label is elephant."

# Image analysis function replacing get_weather
def create_sample_image() -> tuple[str]:
    """Load and encode the elephant image as base64."""
    with open("../multimodal_input/elephant.jpg", "rb") as f:
        image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        image_uri = f"data:image/jpeg;base64,{image_base64}"
    return image_uri



async def main() -> None:
    """Run image analysis with Azure OpenAI and collect telemetry."""
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project,
        AzureAIAgentClient(project_client=project) as client,
    ):
        await client.setup_azure_ai_observability(enable_sensitive_data=True)
        with get_tracer().start_as_current_span(
            name="Input and Image", kind=SpanKind.CLIENT
        ) as current_span:
            print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")
            image_uri = create_sample_image()
            
            agent = ChatAgent(
                chat_client=client,
                name="ImageInspector",
                tools=get_image_data,
                instructions=(
                    "You are an assistant that describes images and returns JSON responses with an embedded data URI."
                ),
            )
            
            async with agent:
                thread = agent.get_new_thread()
                message = ChatMessage(
                    role=Role.USER,
                    contents=[
                        TextContent(
                            text=(
                                "Please analyze the attached image.\n"
                                "1. Describe the image in detail.\n"
                                "2. Return JSON exactly in this format:\n"
                                "{\n"
                                '  "description": "<detailed summary>",\n'
                                '  "image_uri": "data:image/png;base64,<base64 data for the full image>"\n'
                                "}\n"
                                "Return JSON only. The image must be embedded as a data URI using Base64-encoded PNG bytes.\n"
                            )
                        ),
                        DataContent(uri=image_uri, media_type="image/jpeg"),
                    ],
                )
                response = await agent.run(message, thread=thread, store=True)
            # Print the agent’s final assistant message (if present)
            if response.messages:
                assistant_reply = response.messages[-1]
                print("Assistant response:")
                for content in assistant_reply.contents:
                    print(content)


if __name__ == "__main__":
    asyncio.run(main())
