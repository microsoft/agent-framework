# Copyright (c) Microsoft. All rights reserved.


import asyncio
import base64
import json
import os
from datetime import datetime, timezone
from typing import Any
from typing import Annotated
from io import BytesIO

import dotenv
from agent_framework import ChatMessage, DataContent, Role, TextContent, ChatAgent
from agent_framework.observability import get_tracer
from pydantic import Field
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id

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

# Image analysis function replacing get_weather
def create_sample_image() -> tuple[str, str]:
    """Load and encode the elephant image as base64."""
    with open("../multimodal_input/elephant.jpg", "rb") as f:
        image_data = f.read()
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        image_uri = f"data:image/jpeg;base64,{image_base64}"
    return image_uri



async def main() -> None:
    """Run image analysis with Azure OpenAI and collect telemetry."""
    #store = SQLiteImageStore()
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project,
        AzureAIAgentClient(project_client=project) as client,
    ):
        await client.setup_azure_ai_observability(enable_sensitive_data=True)
        with get_tracer().start_as_current_span(
            name="Basic Input and Output for Image Interpretation", kind=SpanKind.CLIENT
        ) as current_span:
            print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")
            image_uri = create_sample_image()

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
            response = await client.get_response(message)
            print(f"Image Response: {response}")



if __name__ == "__main__":
    asyncio.run(main())




