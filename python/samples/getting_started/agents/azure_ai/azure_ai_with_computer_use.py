# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import os
from enum import Enum

from agent_framework import ChatMessage, ChatResponse, DataContent, Role, TextContent
from agent_framework.azure import AzureAIClient
from azure.ai.projects.models import ComputerUsePreviewTool
from azure.identity.aio import AzureCliCredential
from openai.types.responses import ResponseComputerToolCall
from openai.types.responses.response import Response
from openai.types.responses.response_computer_tool_call import Action

"""
Azure AI Agent With Computer Use Tool

This sample demonstrates basic usage of AzureAIClient to create an agent
that can perform computer automation tasks using the ComputerUsePreviewTool.

Pre-requisites:
- Make sure to set up the AZURE_AI_PROJECT_ENDPOINT.
- Make sure to deploy a model that supports the computer use tool, currently "computer-use-preview".

Note that the computer operations in this sample are simulated for demonstration purposes.
"""


class SearchState(Enum):
    """Enum for tracking the state of the simulated web search workflow."""

    INITIAL = "initial"  # Browser search page
    TYPED = "typed"  # Text entered in search box
    PRESSED_ENTER = "pressed_enter"  # Enter key pressed, transitioning to results


def image_to_base64(image_path: str) -> str:
    """Convert an image file to a Base64-encoded string.

    Args:
        image_path: The path to the image file (e.g. 'image_file.png')

    Returns:
        A Base64-encoded string representing the image.

    Raises:
        FileNotFoundError: If the provided file path does not exist.
        OSError: If there's an error reading the file.
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"File not found at: {image_path}")

    try:
        with open(image_path, "rb") as image_file:
            file_data = image_file.read()
        return base64.b64encode(file_data).decode("utf-8")
    except Exception as exc:
        raise OSError(f"Error reading file '{image_path}'") from exc


def load_screenshot_assets() -> dict[str, dict[str, str]]:
    """Load and convert screenshot images to base64 data URLs.

    Returns:
        dict: Dictionary mapping state names to screenshot info with filename and data URL

    Raises:
        FileNotFoundError: If any required screenshot asset files are missing
    """
    # Load demo screenshot images from assets directory
    # Flow: search page -> typed search -> search results
    screenshot_paths = {
        "browser_search": os.path.abspath(os.path.join(os.path.dirname(__file__), "./assets/cua_browser_search.png")),
        "search_typed": os.path.abspath(os.path.join(os.path.dirname(__file__), "./assets/cua_search_typed.png")),
        "search_results": os.path.abspath(os.path.join(os.path.dirname(__file__), "./assets/cua_search_results.png")),
    }

    # Convert images to base64 data URLs with filenames
    screenshots: dict[str, dict[str, str]] = {}
    filename_map = {
        "browser_search": "cua_browser_search.png",
        "search_typed": "cua_search_typed.png",
        "search_results": "cua_search_results.png",
    }

    for key, path in screenshot_paths.items():
        try:
            image_base64 = image_to_base64(path)
            screenshots[key] = {"filename": filename_map[key], "url": f"data:image/png;base64,{image_base64}"}
        except FileNotFoundError as e:
            print(f"Error: Missing required screenshot asset: {e}")
            raise

    return screenshots


def handle_computer_action_and_take_screenshot(
    action: Action,
    current_state: SearchState,
    screenshots: dict[str, dict[str, str]],
):
    """Process a computer action and simulate its execution.

    In a real implementation, you might want to execute real browser operations
    instead of just printing, take screenshots, and return actual screenshot data.

    Args:
        action: The computer action to process (click, type, key press, etc.)
        current_state: Current SearchState of the simulation
        screenshots: Dictionary of screenshot data

    Returns:
        tuple: (screenshot_info, updated_current_state)
    """
    print(f"Executing computer action: {action.type}")

    # State transitions based on actions
    if action.type == "type" and hasattr(action, "text") and action.text:
        current_state = SearchState.TYPED
        print(f"  Typing text: '{action.text}' - Simulating keyboard input")

    # Check for ENTER key press
    elif action.type == "keypress" and action.keys and ("Return" in action.keys or "ENTER" in action.keys):
        current_state = SearchState.PRESSED_ENTER
        print("  -> Detected ENTER key press")

    # Check for click after typing (alternative submit method)
    elif action.type == "click" and current_state == SearchState.TYPED:
        current_state = SearchState.PRESSED_ENTER
        print("  -> Detected click after typing")

    # Provide more realistic feedback based on action type
    if hasattr(action, "x") and hasattr(action, "y"):
        if action.type == "click":
            print(f"  Click at ({action.x}, {action.y}) - Simulating click on UI element")
        elif action.type == "drag":
            path_str = " -> ".join([f"({p.x}, {p.y})" for p in action.path])
            print(f"  Drag path: {path_str} - Simulating drag operation")
        elif action.type == "scroll":
            print(f"  Scroll at ({action.x}, {action.y}) - Simulating scroll action")

    if action.type == "keypress" and action.keys:
        print(f"  Key press: {action.keys} - Simulating key combination")

    if action.type == "screenshot":
        print("  Taking screenshot - Capturing current screen state")

    print(f"  -> Action processed: {action.type}")

    # Determine screenshot based on current state
    if current_state == SearchState.PRESSED_ENTER:
        screenshot_info = screenshots["search_results"]
    elif current_state == SearchState.TYPED:
        screenshot_info = screenshots["search_typed"]
    else:  # SearchState.INITIAL
        screenshot_info = screenshots["browser_search"]

    return screenshot_info, current_state


def print_final_output(openai_response: Response) -> None:
    """Print the final output when the agent completes the task.

    Args:
        openai_response: The inner response object containing the agent's final output
    """
    print("No computer calls found. Agent completed the task:")
    final_output = ""
    for item in openai_response.output:
        if item.type == "message":
            contents = item.content
            for part in contents:
                final_output += getattr(part, "text", None) or getattr(part, "refusal", None) or "" + "\n"

    print(f"Final status: {openai_response.status}")
    print(f"Final output: {final_output.strip()}")


async def main():
    """Main async function to demonstrate Computer Use Agent functionality."""

    async with (
        AzureCliCredential() as credential,
        AzureAIClient(
            async_credential=credential,
            model_deployment_name="computer-use-preview",  # Computer use tool requires specific deployment
        ).create_agent(
            name="ComputerUseAgent",
            instructions="You are a computer automation assistant.",
            tools=[ComputerUsePreviewTool(display_width=1026, display_height=769, environment="windows")],
        ) as agent,
    ):
        print("Starting computer automation session (initial screenshot: cua_browser_search.png)...")

        # Initialize state machine
        current_state = SearchState.INITIAL

        # Load screenshot assets
        try:
            screenshots = load_screenshot_assets()
            print("Successfully loaded screenshot assets")
        except FileNotFoundError:
            print("Failed to load required screenshot assets. Please ensure the asset files exist in ../assets/")
            return

        # Initial user message to start the search task
        messages: list[ChatMessage] = [
            ChatMessage(
                role="user",
                contents=[
                    TextContent(
                        "I need you to help me search for 'OpenAI news'. "
                        "Please type 'OpenAI news' and submit the search. "
                        "Once you see search results, the task is complete."
                    ),
                    DataContent(uri=screenshots["browser_search"]["url"], media_type="image/png"),
                ],
            )
        ]

        agent_thread = agent.get_new_thread()
        response = await agent.run(messages, thread=agent_thread, additional_chat_options={"truncation": "auto"})
        print(f"Initial response received (ID: {response.response_id})")

        # Main interaction loop with deterministic completion
        max_iterations = 10  # Allow enough iterations for completion
        iteration = 0

        while True:
            if iteration >= max_iterations:
                print(f"\nReached maximum iterations ({max_iterations}). Stopping.")
                break

            iteration += 1
            print(f"\n--- Iteration {iteration} ---")

            assert response.raw_representation is not None
            assert isinstance(response.raw_representation, ChatResponse)

            chat_response = response.raw_representation
            assert chat_response.raw_representation is not None
            assert isinstance(chat_response.raw_representation, Response)

            openai_response = chat_response.raw_representation
            computer_calls = [
                computer_call
                for computer_call in openai_response.output
                if isinstance(computer_call, ResponseComputerToolCall)
            ]

            if not computer_calls:
                print_final_output(openai_response)
                break

            # Only process the first computer call
            computer_call = computer_calls[0]
            action = computer_call.action
            call_id = computer_call.call_id
            print(f"Processing computer call ID: {call_id}, Action type: {action.type}")

            # Handle the action and get the screenshot info
            screenshot_info, current_state = handle_computer_action_and_take_screenshot(
                action, current_state, screenshots
            )

            print(f"Sending action result back to agent (using {screenshot_info['filename']})...")
            response = await agent.run(
                ChatMessage(
                    role=Role.TOOL,
                    contents=[],
                    raw_representation={
                        "call_id": call_id,
                        "type": "computer_call_output",
                        "output": {
                            "type": "computer_screenshot",
                            "image_url": screenshot_info["url"],
                        },
                    },
                ),
                thread=agent_thread,
                additional_chat_options={"truncation": "auto"},
            )

            print(f"Follow-up response received (ID: {response.response_id})")


if __name__ == "__main__":
    asyncio.run(main())
