# Copyright (c) Microsoft. All rights reserved.

"""AG-UI client example using AGUIChatClient.

This example demonstrates how to use the AGUIChatClient to connect to
a remote AG-UI server and interact with it using the Agent Framework's
standard chat interface.
"""

import asyncio
import os

from agent_framework_ag_ui import AGUIChatClient


async def main():
    """Main client loop demonstrating AGUIChatClient usage."""
    # Get server URL from environment or use default
    server_url = os.environ.get("AGUI_SERVER_URL", "http://127.0.0.1:5100/")
    print(f"Connecting to AG-UI server at: {server_url}\n")
    print("Using AGUIChatClient with automatic thread management and Agent Framework integration.\n")

    # Create client with context manager for automatic cleanup
    async with AGUIChatClient(endpoint=server_url) as client:
        thread_id: str | None = None

        try:
            while True:
                # Get user input
                message = input("\nUser (:q or quit to exit): ")
                if not message.strip():
                    print("Request cannot be empty.")
                    continue

                if message.lower() in (":q", "quit"):
                    break

                # Send message and stream the response
                print("\nAssistant: ", end="", flush=True)

                # Use metadata to maintain conversation continuity
                metadata = {"thread_id": thread_id} if thread_id else None

                async for update in client.get_streaming_response(message, metadata=metadata):
                    # Extract and display thread ID from first update
                    if not thread_id and update.additional_properties:
                        thread_id = update.additional_properties.get("thread_id")
                        if thread_id:
                            print(f"\n\033[93m[Thread: {thread_id}]\033[0m", end="", flush=True)
                            print("\nAssistant: ", end="", flush=True)

                    # Display text content as it streams
                    from agent_framework import TextContent

                    for content in update.contents:
                        if isinstance(content, TextContent) and content.text:
                            print(f"\033[96m{content.text}\033[0m", end="", flush=True)

                    # Display finish reason if present
                    if update.finish_reason:
                        print(f"\n\033[92m[Finished: {update.finish_reason}]\033[0m", end="", flush=True)

                print()  # New line after response

        except KeyboardInterrupt:
            print("\n\nExiting...")
        except Exception as e:
            print(f"\n\033[91mAn error occurred: {e}\033[0m")


if __name__ == "__main__":
    asyncio.run(main())
