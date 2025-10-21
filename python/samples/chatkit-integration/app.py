# Copyright (c) Microsoft. All rights reserved.

"""
ChatKit Integration Sample with Weather Agent

This sample demonstrates how to integrate Microsoft Agent Framework with OpenAI ChatKit
using a weather tool with widget visualization and Azure OpenAI. It shows a complete
ChatKit server implementation using Agent Framework agents with proper FastAPI setup
and interactive weather widgets.
"""

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from random import randint
from typing import Annotated, Any

import uvicorn
from azure.identity import AzureCliCredential
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import Field

# Agent Framework imports
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework_chatkit import simple_to_agent_input, stream_agent_response, stream_widget

# ChatKit imports
from chatkit.server import ChatKitServer
from chatkit.types import ThreadMetadata, ThreadStreamEvent, UserMessageItem

# Local imports
from store import SQLiteStore
from weather_widget import WeatherData, render_weather_widget, weather_widget_copy_text


# Global variable to store weather data for widget creation
_last_weather_data: WeatherData | None = None


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location.

    Returns a text description and stores data for widget creation.
    """
    global _last_weather_data

    conditions = ["sunny", "cloudy", "rainy", "stormy", "snowy", "foggy"]
    temperature = randint(-5, 35)
    condition = conditions[randint(0, len(conditions) - 1)]

    # Add some realistic details
    humidity = randint(30, 90)
    wind_speed = randint(5, 25)

    # Store data for widget creation
    _last_weather_data = WeatherData(
        location=location,
        condition=condition,
        temperature=temperature,
        humidity=humidity,
        wind_speed=wind_speed,
    )

    # Return text description
    return (
        f"Weather in {location}:\n"
        f"• Condition: {condition.title()}\n"
        f"• Temperature: {temperature}°C\n"
        f"• Humidity: {humidity}%\n"
        f"• Wind: {wind_speed} km/h"
    )


def get_time() -> str:
    """Get the current UTC time."""
    current_time = datetime.now(timezone.utc)
    return f"Current UTC time: {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC"


class WeatherChatKitServer(ChatKitServer[dict[str, Any]]):
    """ChatKit server implementation using Agent Framework.

    This server integrates Agent Framework agents with ChatKit's server protocol,
    providing weather information with interactive widgets and time queries through Azure OpenAI.
    """

    def __init__(self, data_store: SQLiteStore):
        super().__init__(data_store)

        # Create Agent Framework agent with Azure OpenAI
        # For authentication, run `az login` command in terminal
        self.weather_agent = ChatAgent(
            chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
            instructions=(
                "You are a helpful weather assistant. You can provide weather information "
                "for any location and tell the current time. Be friendly and informative "
                "in your responses. When you provide weather information, a beautiful "
                "interactive weather widget will be displayed to the user automatically."
            ),
            tools=[get_weather, get_time],
        )

    async def respond(
        self,
        thread: ThreadMetadata,
        input_user_message: UserMessageItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        """Handle incoming user messages and generate responses.

        This method converts ChatKit messages to Agent Framework format,
        runs the agent, converts the response back to ChatKit events,
        and creates interactive weather widgets when weather data is queried.
        """
        global _last_weather_data

        if input_user_message is None:
            return

        try:
            # Reset weather data
            _last_weather_data = None

            # Convert ChatKit input to Agent Framework messages
            agent_messages = await simple_to_agent_input(input_user_message)

            if not agent_messages:
                return

            # Run the Agent Framework agent with streaming
            response_stream = self.weather_agent.run_stream(agent_messages)

            # Convert Agent Framework response to ChatKit events
            async for event in stream_agent_response(response_stream, thread.id):
                yield event

            # If weather data was collected during the tool call, create a widget
            if _last_weather_data is not None:
                # Create weather widget
                widget = render_weather_widget(_last_weather_data)
                copy_text = weather_widget_copy_text(_last_weather_data)

                # Stream the widget
                async for widget_event in stream_widget(
                    thread_id=thread.id, widget=widget, copy_text=copy_text
                ):
                    yield widget_event

        except Exception as e:
            # In a real application, you'd want better error handling and logging
            print(f"Error processing message: {e}")
            import traceback

            traceback.print_exc()




# FastAPI application setup
app = FastAPI(
    title="ChatKit Weather Agent",
    description="Weather assistant powered by Agent Framework and Azure OpenAI",
    version="1.0.0"
)

# Add CORS middleware to allow frontend connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize data store and ChatKit server
data_store = SQLiteStore()
chatkit_server = WeatherChatKitServer(data_store)


@app.post("/chatkit")
async def chatkit_endpoint(request: Request):
    """Main ChatKit endpoint that handles all ChatKit requests.

    This endpoint follows the ChatKit server protocol and handles both
    streaming and non-streaming responses.
    """
    request_body = await request.body()

    # Create context following the working examples pattern
    context = {"request": request}

    # Process the request using ChatKit server
    result = await chatkit_server.process(request_body, context)

    # Return appropriate response type
    if hasattr(result, '__aiter__'):  # StreamingResult
        return StreamingResponse(result, media_type="text/event-stream")  # type: ignore[arg-type]
    else:  # NonStreamingResult
        return Response(content=result.json, media_type="application/json")  # type: ignore[union-attr]


if __name__ == "__main__":
    # Run the server on port 8001 to match frontend proxy configuration
    uvicorn.run(app, host="0.0.0.0", port=8001)
