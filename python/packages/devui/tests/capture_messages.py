#!/usr/bin/env python3
# Copyright (c) Microsoft. All rights reserved.

"""
Message Capture Script - Debug message flow 
- This script is intended to provide a reference for the types of events that are emitted by the server when agents and workflows are executed  
"""

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import requests
import uvicorn
from openai import OpenAI

from agent_framework_devui import DevServer


def start_server() -> tuple[str, Any]:
    """Start server with examples directory."""
    # Get examples directory
    current_dir = Path(__file__).parent
    examples_dir = current_dir.parent / "examples"

    # Create and start server with simplified parameters
    server = DevServer(
        entities_dir=str(examples_dir.resolve()),
        host="127.0.0.1",
        port=8085,  # Use different port
        ui_enabled=False
    )

    print("🔍 Starting DevServer on port 8085...")

    app = server.get_app()

    server_config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=8085,
        log_level="info"  # More verbose to see tracing setup
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
            response = requests.get("http://127.0.0.1:8085/health", timeout=5)
            if response.status_code == 200:
                print("✅ Server started successfully!")
                break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⏳ Server not ready yet (attempt {attempt + 1}/{max_retries}), waiting...")
                time.sleep(2)
            else:
                raise RuntimeError(f"Server failed to start after {max_retries} attempts: {e}")

    return "http://127.0.0.1:8085", server_instance


def capture_agent_stream_with_tracing(client: OpenAI, agent_id: str, scenario: str = "success") -> List[Dict[str, Any]]:
    """Capture agent streaming events."""
    print(f"🔍 Capturing agent streaming events for {agent_id} - {scenario} scenario...")

    try:
        stream = client.responses.create(
            model="agent-framework",
            input="Tell me about the weather in Tokyo. I want details.",
            stream=True,
            extra_body={
                "entity_id": agent_id
            }
        )

        events = []
        for event in stream:
            # Serialize the entire event object
            try:
                event_dict = json.loads(event.model_dump_json())
            except:
                # Fallback to dict conversion if model_dump_json fails
                event_dict = event.__dict__ if hasattr(event, "__dict__") else str(event)

            events.append(event_dict)

            # Just capture everything as-is
            if len(events) >= 200:  # Increased limit
                break

        print(f"📊 Captured {len(events)} total events")
        return events

    except Exception as e:
        print(f"❌ Error during agent stream capture ({scenario}): {str(e)}")
        # Return error information as events
        error_event = {
            "type": "error",
            "scenario": scenario,
            "error_message": str(e),
            "error_type": type(e).__name__,
            "timestamp": time.time()
        }
        return [error_event]


def capture_workflow_stream_with_tracing(client: OpenAI, workflow_id: str, scenario: str = "success") -> List[Dict[str, Any]]:
    """Capture workflow streaming events."""
    print(f"🔍 Capturing workflow streaming events for {workflow_id} - {scenario} scenario...")

    try:
        stream = client.responses.create(
            model="agent-framework",
            input="Process this spam detection workflow with multiple emails: 'Buy now!', 'Hello mom', 'URGENT: Click here!'",
            stream=True,
            extra_body={
                "entity_id": workflow_id
            }
        )

        events = []
        for event in stream:
            # Serialize the entire event object
            try:
                event_dict = json.loads(event.model_dump_json())
            except:
                # Fallback to dict conversion if model_dump_json fails
                event_dict = event.__dict__ if hasattr(event, "__dict__") else str(event)

            events.append(event_dict)

            # Just capture everything as-is
            if len(events) >= 200:  # Increased limit
                break

        print(f"📊 Captured {len(events)} total workflow events")
        return events

    except Exception as e:
        print(f"❌ Error during workflow stream capture ({scenario}): {str(e)}")
        # Return error information as events
        error_event = {
            "type": "error",
            "scenario": scenario,
            "error_message": str(e),
            "error_type": type(e).__name__,
            "timestamp": time.time(),
            "entity_type": "workflow"
        }
        return [error_event]


def capture_agent_with_bad_config(base_url: str, agent_id: str) -> List[Dict[str, Any]]:
    """Capture agent events with intentionally bad configuration to test error handling."""
    print(f"🔍 Testing agent with BAD CONFIGURATION for {agent_id}...")

    # Test with invalid API key
    bad_client = OpenAI(
        base_url=f"{base_url}/v1",
        api_key="invalid-api-key-123"
    )

    try:
        events = capture_agent_stream_with_tracing(bad_client, agent_id, "bad_api_key")
        return events
    except Exception as e:
        print(f"❌ Caught exception with bad API key: {str(e)}")
        return [{
            "type": "error",
            "scenario": "bad_api_key",
            "error_message": str(e),
            "error_type": type(e).__name__,
            "timestamp": time.time()
        }]


def capture_agent_with_wrong_model(base_url: str, agent_id: str) -> List[Dict[str, Any]]:
    """Capture agent events with wrong model name to test error handling."""
    print(f"🔍 Testing agent with WRONG MODEL for {agent_id}...")

    client = OpenAI(
        base_url=f"{base_url}/v1",
        api_key="dummy-key"  # Use the same key as success case
    )

    try:
        stream = client.responses.create(
            model="gpt-4-nonexistent-model",  # Wrong model name
            input="Tell me about the weather in Tokyo. I want details.",
            stream=True,
            extra_body={
                "entity_id": agent_id
            }
        )

        events = []
        for event in stream:
            # Serialize the entire event object
            try:
                event_dict = json.loads(event.model_dump_json())
            except:
                # Fallback to dict conversion if model_dump_json fails
                event_dict = event.__dict__ if hasattr(event, "__dict__") else str(event)

            events.append(event_dict)

            if len(events) >= 200:
                break

        return events

    except Exception as e:
        print(f"❌ Caught exception with wrong model: {str(e)}")
        return [{
            "type": "error",
            "scenario": "wrong_model",
            "error_message": str(e),
            "error_type": type(e).__name__,
            "timestamp": time.time()
        }]


def main():
    """Main capture script - testing both success and failure scenarios."""
    print("🚀 Starting Message Capture Script (Success + Failure scenarios)...")

    # Setup
    output_dir = Path(__file__).parent / "captured_messages"
    output_dir.mkdir(exist_ok=True)
    print(f"Output directory: {output_dir}")

    # Start server
    base_url, server_instance = start_server()

    try:
        # Create OpenAI client for success scenario
        client = OpenAI(
            base_url=f"{base_url}/v1",
            api_key="dummy-key"
        )

        # Discover entities
        discovery_response = requests.get(f"{base_url}/v1/entities", timeout=10)
        entities = discovery_response.json()["entities"]

        all_results = {}

        # Test each entity
        for entity in entities:
            entity_type = entity["type"]
            entity_id = entity["id"]
            entity_name = entity["name"]

            print(f"\n📝 Testing {entity_type.upper()}: {entity_name} ({entity_id})")

            if entity_type == "agent":
                events = capture_agent_stream_with_tracing(client, entity_id, "success")
            elif entity_type == "workflow":
                events = capture_workflow_stream_with_tracing(client, entity_id, "success")
            else:
                continue

            all_results[f"{entity_type}_{entity_id}"] = {
                "entity_info": entity,
                "events": events
            }
        # Save results
        file_path = output_dir / "entities_stream_events.json"
        with open(file_path, "w") as f:
            json.dump({
                "timestamp": time.time(),
                "server_type": "DevServer",
                "entities_tested": all_results
            }, f, indent=2, default=str)

        print(f"\n📊 RESULTS: Saved {len(all_results)} entities to {file_path.name}")
        for key, result in all_results.items():
            entity_info = result["entity_info"]
            print(f"   {entity_info['type']}: {entity_info['name']} - {len(result['events'])} events")

    finally:
        # Cleanup server
        try:
            server_instance.should_exit = True
        except:
            pass


if __name__ == "__main__":
    main()
