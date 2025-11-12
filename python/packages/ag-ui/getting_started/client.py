# Copyright (c) Microsoft. All rights reserved.

"""AG-UI client example."""

import asyncio
import json
import os
from collections.abc import AsyncIterator

import httpx


class AGUIClient:
    """Simple AG-UI protocol client."""

    def __init__(self, server_url: str):
        """Initialize the client.

        Args:
            server_url: The AG-UI server endpoint URL
        """
        self.server_url = server_url
        self.thread_id: str | None = None

    async def send_message(self, message: str) -> AsyncIterator[dict]:
        """Send a message and stream the response.

        Args:
            message: The user message to send

        Yields:
            AG-UI events from the server
        """
        # Prepare the request
        request_data: dict[str, object] = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": message},
            ]
        }

        # Include thread_id if we have one (for conversation continuity)
        if self.thread_id:
            request_data["thread_id"] = self.thread_id

        # Stream the response
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                self.server_url,
                json=request_data,
                headers={"Accept": "text/event-stream"},
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    # Parse Server-Sent Events format
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix
                        try:
                            event = json.loads(data)
                            yield event

                            # Capture thread_id from RUN_STARTED event
                            if event.get("type") == "RUN_STARTED" and not self.thread_id:
                                self.thread_id = event.get("threadId")
                        except json.JSONDecodeError:
                            continue


async def main():
    """Main client loop."""
    # Get server URL from environment or use default
    server_url = os.environ.get("AGUI_SERVER_URL", "http://127.0.0.1:5100/")
    print(f"Connecting to AG-UI server at: {server_url}\n")

    client = AGUIClient(server_url)

    try:
        while True:
            # Get user input
            message = input("\nUser (:q or quit to exit): ")
            if not message.strip():
                print("Request cannot be empty.")
                continue

            if message.lower() in (":q", "quit"):
                break

            # Send message and display streaming response
            print("\n", end="")
            async for event in client.send_message(message):
                event_type = event.get("type", "")

                if event_type == "RUN_STARTED":
                    thread_id = event.get("threadId", "")
                    run_id = event.get("runId", "")
                    print(f"\033[93m[Run Started - Thread: {thread_id}, Run: {run_id}]\033[0m")

                elif event_type == "TEXT_MESSAGE_CONTENT":
                    # Stream text content in cyan
                    print(f"\033[96m{event.get('delta', '')}\033[0m", end="", flush=True)

                elif event_type == "RUN_FINISHED":
                    thread_id = event.get("threadId", "")
                    run_id = event.get("runId", "")
                    print(f"\n\033[92m[Run Finished - Thread: {thread_id}, Run: {run_id}]\033[0m")

                elif event_type == "RUN_ERROR":
                    error_message = event.get("message", "Unknown error")
                    print(f"\n\033[91m[Run Error - Message: {error_message}]\033[0m")

            print()

    except KeyboardInterrupt:
        print("\n\nExiting...")
    except Exception as e:
        print(f"\n\033[91mAn error occurred: {e}\033[0m")


if __name__ == "__main__":
    asyncio.run(main())
