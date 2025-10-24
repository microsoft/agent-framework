# Copyright (c) Microsoft. All rights reserved.

"""
ChatKit Integration Sample with Weather Agent and Image Analysis

This sample demonstrates how to integrate Microsoft Agent Framework with OpenAI ChatKit
using a weather tool with widget visualization, image analysis, and Azure OpenAI. It shows 
a complete ChatKit server implementation using Agent Framework agents with proper FastAPI 
setup, interactive weather widgets, and vision capabilities for analyzing uploaded images.
"""

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from random import randint
from typing import Annotated, Any
from collections.abc import Callable

import uvicorn
from azure.identity import AzureCliCredential
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import Field

# ============================================================================
# Configuration Constants
# ============================================================================

# Server configuration
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8001
SERVER_BASE_URL = f"http://localhost:{SERVER_PORT}"

# Database configuration
DATABASE_PATH = "chatkit_demo.db"

# File storage configuration
UPLOADS_DIRECTORY = "./uploads"

# User context
DEFAULT_USER_ID = "demo_user"

# Logging configuration
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ============================================================================
# Logging Setup
# ============================================================================

logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
)
logger = logging.getLogger(__name__)

# Agent Framework imports
from agent_framework import ChatAgent, ChatMessage, Role
from agent_framework.azure import AzureOpenAIChatClient

# Agent Framework ChatKit integration
from agent_framework_chatkit import ThreadItemConverter, stream_agent_response

# ChatKit imports
from chatkit.actions import Action
from chatkit.server import ChatKitServer
from chatkit.store import StoreItemType, default_generate_id
from chatkit.types import (
    ThreadItemDoneEvent,
    ThreadMetadata,
    ThreadStreamEvent,
    UserMessageItem,
    WidgetItem,
)
from chatkit.widgets import WidgetRoot

# Local imports
from attachment_store import FileBasedAttachmentStore
from store import SQLiteStore
from weather_widget import (
    WeatherData,
    city_selector_copy_text,
    render_city_selector_widget,
    render_weather_widget,
    weather_widget_copy_text,
)


# Global variable to store weather data for widget creation
_last_weather_data: WeatherData | None = None
# Global flag to show city selector
_show_city_selector: bool = False


async def stream_widget(
    thread_id: str,
    widget: WidgetRoot,
    copy_text: str | None = None,
    generate_id: Callable[[StoreItemType], str] = default_generate_id,
) -> AsyncIterator[ThreadStreamEvent]:
    """Stream a ChatKit widget as a ThreadStreamEvent.

    This helper function creates a ChatKit widget item and yields it as a
    ThreadItemDoneEvent that can be consumed by the ChatKit UI.

    Args:
        thread_id: The ChatKit thread ID for the conversation.
        widget: The ChatKit widget to display.
        copy_text: Optional text representation of the widget for copy/paste.
        generate_id: Optional function to generate IDs for ChatKit items.

    Yields:
        ThreadStreamEvent: ChatKit event containing the widget.
    """
    item_id = generate_id("message")

    widget_item = WidgetItem(
        id=item_id,
        thread_id=thread_id,
        created_at=datetime.now(),
        widget=widget,
        copy_text=copy_text,
    )

    yield ThreadItemDoneEvent(type="thread.item.done", item=widget_item)


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location.

    Returns a text description and stores data for widget creation.
    """
    global _last_weather_data

    logger.info(f"Fetching weather for location: {location}")

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

    logger.debug(
        f"Weather data generated: {condition}, {temperature}°C, {humidity}% humidity, {wind_speed} km/h wind"
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
    logger.info("Getting current UTC time")
    return f"Current UTC time: {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC"


def show_city_selector() -> str:
    """Show an interactive city selector widget to the user.

    This function triggers the display of a widget that allows users
    to select from popular cities to get weather information.
    """
    global _show_city_selector
    logger.info("Activating city selector widget")
    _show_city_selector = True
    return "I'll show you a list of cities to choose from."


class WeatherChatKitServer(ChatKitServer[dict[str, Any]]):
    """ChatKit server implementation using Agent Framework.

    This server integrates Agent Framework agents with ChatKit's server protocol,
    providing weather information with interactive widgets and time queries through Azure OpenAI.
    """

    def __init__(self, data_store: SQLiteStore, attachment_store: FileBasedAttachmentStore):
        super().__init__(data_store, attachment_store)

        logger.info("Initializing WeatherChatKitServer")

        # Create Agent Framework agent with Azure OpenAI
        # For authentication, run `az login` command in terminal
        try:
            self.weather_agent = ChatAgent(
                chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
                instructions=(
                    "You are a helpful weather assistant with image analysis capabilities. "
                    "You can provide weather information for any location, tell the current time, "
                    "and analyze images that users upload. Be friendly and informative in your responses.\n\n"
                    "When you provide weather information, a beautiful interactive weather widget will be "
                    "displayed to the user automatically.\n\n"
                    "If a user asks to see a list of cities or wants to choose from available cities, "
                    "use the show_city_selector tool to display an interactive city selector.\n\n"
                    "When users upload images, you will automatically receive them and can analyze their content. "
                    "Describe what you see in detail and be helpful in answering questions about the images."
                ),
                tools=[get_weather, get_time, show_city_selector],
            )
            logger.info("Weather agent initialized successfully with Azure OpenAI")
        except Exception as e:
            logger.error(f"Failed to initialize weather agent: {e}")
            raise

        # Create ThreadItemConverter with attachment data fetcher
        self.converter = ThreadItemConverter(
            attachment_data_fetcher=self._fetch_attachment_data,
        )

        logger.info("WeatherChatKitServer initialized")

    async def _fetch_attachment_data(self, attachment_id: str) -> bytes:
        """Fetch attachment binary data for the converter.

        Args:
            attachment_id: The ID of the attachment to fetch.

        Returns:
            The binary data of the attachment.
        """
        return await attachment_store.read_attachment_bytes(attachment_id)

    async def respond(
        self,
        thread: ThreadMetadata,
        input_user_message: UserMessageItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        """Handle incoming user messages and generate responses.

        This method converts ChatKit messages to Agent Framework format using ThreadItemConverter,
        runs the agent, converts the response back to ChatKit events using stream_agent_response,
        and creates interactive weather widgets when weather data is queried.
        """
        global _last_weather_data, _show_city_selector

        if input_user_message is None:
            logger.debug("Received None user message, skipping")
            return

        logger.info(f"Processing message for thread: {thread.id}")

        try:
            # Reset weather data and city selector flag
            _last_weather_data = None
            _show_city_selector = False

            # Convert ChatKit user message to Agent Framework ChatMessage using ThreadItemConverter
            agent_messages = await self.converter.to_agent_input(input_user_message)
            
            if not agent_messages:
                logger.warning("No messages after conversion")
                return

            logger.info(f"Running agent with {len(agent_messages)} message(s)")

            # Run the Agent Framework agent with streaming and convert to ChatKit events
            async for event in stream_agent_response(
                self.weather_agent.run_stream(agent_messages),
                thread_id=thread.id,
            ):
                yield event

            # If weather data was collected during the tool call, create a widget
            if _last_weather_data is not None:
                logger.info(f"Creating weather widget for location: {_last_weather_data.location}")
                # Create weather widget
                widget = render_weather_widget(_last_weather_data)
                copy_text = weather_widget_copy_text(_last_weather_data)

                # Stream the widget
                async for widget_event in stream_widget(
                    thread_id=thread.id, widget=widget, copy_text=copy_text
                ):
                    yield widget_event
                logger.debug("Weather widget streamed successfully")

            # If city selector should be shown, create and stream that widget
            if _show_city_selector:
                logger.info("Creating city selector widget")
                # Create city selector widget
                selector_widget = render_city_selector_widget()
                selector_copy_text = city_selector_copy_text()

                # Stream the widget
                async for widget_event in stream_widget(
                    thread_id=thread.id, widget=selector_widget, copy_text=selector_copy_text
                ):
                    yield widget_event
                logger.debug("City selector widget streamed successfully")

            logger.info(f"Completed processing message for thread: {thread.id}")

        except Exception as e:
            logger.error(f"Error processing message for thread {thread.id}: {e}", exc_info=True)

    async def action(
        self,
        thread: ThreadMetadata,
        action: Action[str, Any],
        sender: WidgetItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        """Handle widget actions from the frontend.

        This method processes actions triggered by interactive widgets,
        such as city selection from the city selector widget.
        """
        global _last_weather_data

        logger.info(f"Received action: {action.type} for thread: {thread.id}")

        if action.type == "city_selected":
            # Extract city information from the action payload
            city_label = action.payload.get("city_label", "Unknown")

            logger.info(f"City selected: {city_label}")
            logger.debug(f"Action payload: {action.payload}")

            # Reset weather data
            _last_weather_data = None

            # Create an agent message asking about the weather
            agent_messages = [ChatMessage(role=Role.USER, text=f"What's the weather in {city_label}?")]

            logger.debug(f"Processing weather query: {agent_messages[0].text}")

            # Run the Agent Framework agent with streaming and convert to ChatKit events
            async for event in stream_agent_response(
                self.weather_agent.run_stream(agent_messages),
                thread_id=thread.id,
            ):
                yield event

            # If weather data was collected during the tool call, create a widget
            if _last_weather_data is not None:
                logger.info(f"Creating weather widget for: {_last_weather_data.location}")
                # Create weather widget
                widget = render_weather_widget(_last_weather_data)
                copy_text = weather_widget_copy_text(_last_weather_data)

                # Stream the widget
                async for widget_event in stream_widget(
                    thread_id=thread.id, widget=widget, copy_text=copy_text
                ):
                    yield widget_event
                logger.debug("Weather widget created successfully from action")
            else:
                logger.warning("No weather data available to create widget after action")


# FastAPI application setup
app = FastAPI(
    title="ChatKit Weather & Vision Agent",
    description="Weather and image analysis assistant powered by Agent Framework and Azure OpenAI",
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
logger.info("Initializing application components")
data_store = SQLiteStore(db_path=DATABASE_PATH)
attachment_store = FileBasedAttachmentStore(
    uploads_dir=UPLOADS_DIRECTORY,
    base_url=SERVER_BASE_URL,
    data_store=data_store,
)
chatkit_server = WeatherChatKitServer(data_store, attachment_store)
logger.info("Application initialization complete")


@app.post("/chatkit")
async def chatkit_endpoint(request: Request):
    """Main ChatKit endpoint that handles all ChatKit requests.

    This endpoint follows the ChatKit server protocol and handles both
    streaming and non-streaming responses.
    """
    logger.debug(f"Received ChatKit request from {request.client}")
    request_body = await request.body()

    # Create context following the working examples pattern
    context = {"request": request}

    try:
        # Process the request using ChatKit server
        result = await chatkit_server.process(request_body, context)

        # Return appropriate response type
        if hasattr(result, '__aiter__'):  # StreamingResult
            logger.debug("Returning streaming response")
            return StreamingResponse(result, media_type="text/event-stream")  # type: ignore[arg-type]
        else:  # NonStreamingResult
            logger.debug("Returning non-streaming response")
            return Response(content=result.json, media_type="application/json")  # type: ignore[union-attr]
    except Exception as e:
        logger.error(f"Error processing ChatKit request: {e}", exc_info=True)
        raise


@app.post("/upload/{attachment_id}")
async def upload_file(attachment_id: str, file: UploadFile = File(...)):
    """Handle file upload for two-phase upload.

    The client POSTs the file bytes here after creating the attachment
    via the ChatKit attachments.create endpoint.
    """
    logger.info(f"Receiving file upload for attachment: {attachment_id}")
    
    try:
        # Read file contents
        contents = await file.read()
        
        # Save to disk
        file_path = attachment_store.get_file_path(attachment_id)
        file_path.write_bytes(contents)
        
        logger.info(f"Saved {len(contents)} bytes to {file_path}")
        
        # Load the attachment metadata from the data store
        attachment = await data_store.load_attachment(attachment_id, {"user_id": DEFAULT_USER_ID})
        
        # Clear the upload_url since upload is complete
        attachment.upload_url = None
        
        # Save the updated attachment back to the store
        await data_store.save_attachment(attachment, {"user_id": DEFAULT_USER_ID})
        
        # Return the attachment metadata as JSON
        return JSONResponse(content=attachment.model_dump(mode="json"))
        
    except Exception as e:
        logger.error(f"Error uploading file for attachment {attachment_id}: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to upload file: {str(e)}"}
        )


@app.get("/preview/{attachment_id}")
async def preview_image(attachment_id: str):
    """Serve image preview/thumbnail.

    For simplicity, this serves the full image. In production, you should
    generate and cache thumbnails.
    """
    logger.debug(f"Serving preview for attachment: {attachment_id}")
    
    try:
        file_path = attachment_store.get_file_path(attachment_id)
        
        if not file_path.exists():
            return JSONResponse(status_code=404, content={"error": "File not found"})
        
        # Determine media type from file extension or attachment metadata
        # For simplicity, we'll try to load from the store
        try:
            attachment = await data_store.load_attachment(attachment_id, {"user_id": DEFAULT_USER_ID})
            media_type = attachment.mime_type
        except Exception:
            # Default to binary if we can't determine
            media_type = "application/octet-stream"
        
        return FileResponse(file_path, media_type=media_type)
        
    except Exception as e:
        logger.error(f"Error serving preview for attachment {attachment_id}: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    # Run the server
    logger.info(f"Starting ChatKit Weather Agent server on {SERVER_HOST}:{SERVER_PORT}")
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")
