# Copyright (c) Microsoft. All rights reserved.

"""
Message Capture Script - Debug message flow
- This script is intended to provide a reference for the types of events
  that are emitted by the server when agents and workflows are executed
"""

import asyncio
import contextlib
import http.client
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn
from openai import OpenAI

from agent_framework_devui import DevServer

logger = logging.getLogger(__name__)


def start_server() -> tuple[str, Any]:
    """Start server with samples directory."""
    # Get samples directory - updated path after samples were moved
    current_dir = Path(__file__).parent
    # Samples are now in python/samples/getting_started/devui
    samples_dir = current_dir.parent.parent.parent / "samples" / "getting_started" / "devui"

    if not samples_dir.exists():
        raise RuntimeError(f"Samples directory not found: {samples_dir}")

    logger.info(f"Using samples directory: {samples_dir}")

    # Create and start server with simplified parameters
    server = DevServer(
        entities_dir=str(samples_dir.resolve()),
        host="127.0.0.1",
        port=8085,  # Use different port
        ui_enabled=False,
    )

    app = server.get_app()

    server_config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=8085,
        # log_level="info",  # More verbose to see tracing setup
    )
    server_instance = uvicorn.Server(server_config)

    def run_server():
        asyncio.run(server_instance.serve())

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait for server to start
    time.sleep(5)  # Increased wait time

    # Verify server is running with retries
    max_retries = 10
    for attempt in range(max_retries):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", 8085, timeout=5)
            try:
                conn.request("GET", "/health")
                response = conn.getresponse()
                if response.status == 200:
                    break
            finally:
                conn.close()
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise RuntimeError(f"Server failed to start after {max_retries} attempts: {e}") from e

    return "http://127.0.0.1:8085", server_instance


def capture_agent_stream_with_tracing(client: OpenAI, agent_id: str, scenario: str = "success") -> list[dict[str, Any]]:
    """Capture agent streaming events."""

    try:
        stream = client.responses.create(
            metadata={"entity_id": agent_id},
            input="Tell me about the weather in Tokyo. I want details.",
            stream=True,
        )

        events = []
        for event in stream:
            # Serialize the entire event object
            try:
                event_dict = json.loads(event.model_dump_json())
            except Exception:
                # Fallback to dict conversion if model_dump_json fails
                event_dict = event.__dict__ if hasattr(event, "__dict__") else str(event)

            events.append(event_dict)

            # Just capture everything as-is
            if len(events) >= 200:  # Increased limit
                break

        return events

    except Exception as e:
        # Return error information as events
        error_event = {
            "type": "error",
            "scenario": scenario,
            "error_message": str(e),
            "error_type": type(e).__name__,
            "timestamp": time.time(),
        }
        return [error_event]


def capture_workflow_stream_with_tracing(
    client: OpenAI, workflow_id: str, scenario: str = "success"
) -> list[dict[str, Any]]:
    """Capture workflow streaming events."""

    try:
        stream = client.responses.create(
            metadata={"entity_id": workflow_id},
            input=(
                "Process this spam detection workflow with multiple emails: "
                "'Buy now!', 'Hello mom', 'URGENT: Click here!'"
            ),
            stream=True,
        )

        events = []
        for event in stream:
            # Serialize the entire event object
            try:
                event_dict = json.loads(event.model_dump_json())
            except Exception:
                # Fallback to dict conversion if model_dump_json fails
                event_dict = event.__dict__ if hasattr(event, "__dict__") else str(event)

            events.append(event_dict)

            # Just capture everything as-is
            if len(events) >= 200:  # Increased limit
                break

        return events

    except Exception as e:
        # Return error information as events
        error_event = {
            "type": "error",
            "scenario": scenario,
            "error_message": str(e),
            "error_type": type(e).__name__,
            "timestamp": time.time(),
            "entity_type": "workflow",
        }
        return [error_event]


def main():
    """Main capture script - testing both success and failure scenarios."""

    # Setup
    output_dir = Path(__file__).parent / "captured_messages"
    output_dir.mkdir(exist_ok=True)

    # Start server
    base_url, server_instance = start_server()

    try:
        # Create OpenAI client for success scenario
        client = OpenAI(base_url=f"{base_url}/v1", api_key="dummy-key")

        # Discover entities
        conn = http.client.HTTPConnection("127.0.0.1", 8085, timeout=10)
        try:
            conn.request("GET", "/v1/entities")
            response = conn.getresponse()
            response_data = response.read().decode("utf-8")
            entities = json.loads(response_data)["entities"]
        finally:
            conn.close()

        all_results = {}

        # Test each entity
        for entity in entities:
            entity_type = entity["type"]
            entity_id = entity["id"]

            if entity_type == "agent":
                events = capture_agent_stream_with_tracing(client, entity_id, "success")
            elif entity_type == "workflow":
                events = capture_workflow_stream_with_tracing(client, entity_id, "success")
            else:
                continue

            all_results[f"{entity_type}_{entity_id}"] = {"entity_info": entity, "events": events}
        # Save results
        file_path = output_dir / "entities_stream_events.json"
        with open(file_path, "w") as f:
            json.dump(
                {"timestamp": time.time(), "server_type": "DevServer", "entities_tested": all_results},
                f,
                indent=2,
                default=str,
            )

    finally:
        # Cleanup server
        with contextlib.suppress(Exception):
            server_instance.should_exit = True


if __name__ == "__main__":
    main()
