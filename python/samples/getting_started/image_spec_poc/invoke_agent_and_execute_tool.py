# Copyright (c) Microsoft. All rights reserved.


import asyncio
import base64
import json
import os
from typing import Any, Annotated

import dotenv
from agent_framework import ChatMessage, DataContent, Role, TextContent, ChatAgent
from agent_framework.observability import get_tracer
from agent_framework.azure import AzureAIClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import Field


# For loading the `AZURE_AI_PROJECT_ENDPOINT` environment variable
dotenv.load_dotenv()


def load_sample_image() -> str:
    """Load and encode the elephant image as base64 data URI."""
    with open("../multimodal_input/elephant.jpg", "rb") as f:
        image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        image_uri = f"data:image/jpeg;base64,{image_base64}"
    return image_uri


async def store_image_analysis(
    description: Annotated[str, Field(description="A detailed description of the image")],
    main_subject: Annotated[str, Field(description="The main subject of the image")],
    image_uri: Annotated[str, Field(description="The data URI of the image (can be shortened/truncated)")],
) -> str:
    """Store the image analysis results including the image URI. Call this after analyzing an image."""
    print(f"\n[Tool Called] Storing analysis:")
    print(f"  Main subject: {main_subject}")
    print(f"  Description: {description[:100]}...")
    print(f"  Image URI: {image_uri}")
    
    # In a real app, you'd save this to a database
    return f"Successfully stored analysis for '{main_subject}' with image_uri"



async def main() -> None:
    """Run image analysis with Azure OpenAI and collect telemetry."""
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project,
        AzureAIClient(project_client=project, agent_name="ImageAnalyzerAgent") as client,
    ):
        await client.setup_azure_ai_observability(enable_sensitive_data=True)
        with get_tracer().start_as_current_span(
            name="Image Analysis", kind=SpanKind.CLIENT
        ) as current_span:
            print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")
            
            # Load the image
            image_uri = load_sample_image()
            
            agent = ChatAgent(
                chat_client=client,
                name="ImageInspector",
                tools=[store_image_analysis],
                instructions=(
                    "You are an assistant that analyzes images. "
                    "After analyzing an image, use the store_image_analysis tool to save the results. "
                    "For image_uri, you can pass a shortened/truncated version of the data URI."
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
