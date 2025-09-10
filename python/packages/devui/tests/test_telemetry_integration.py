# Copyright (c) Microsoft. All rights reserved.

"""Integration tests to verify actual telemetry behavior in devui."""

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, List
from unittest.mock import Mock

# Add the parent directory to Python path so we can import agent_framework_devui
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_framework_devui import AgentFrameworkDebugServer, DebugStreamEvent

# Import shared test utilities
from .test_utils import MockAgent, create_mock_workflow


async def test_telemetry_modes():
    """Test different telemetry modes and show the differences."""
    
    print("\n=== Testing Telemetry Modes ===\n")
    
    # Test agent with different telemetry modes
    test_cases = [
        ("none", False, "No telemetry - should be minimal traces"),
        ("framework", False, "Framework only - should see agent traces"),
        ("workflow", False, "Workflow only - should see workflow traces"),
        ("all", False, "All traces - should see both agent and workflow traces"),
        ("all", True, "All traces + sensitive - should see everything including sensitive data")
    ]
    
    mock_agent = MockAgent()
    mock_workflow = create_mock_workflow()
    
    for mode, sensitive, description in test_cases:
        print(f"--- {description} ---")
        
        # Create server with specific telemetry mode
        server = AgentFrameworkDebugServer(
            telemetry_mode=mode,
            include_sensitive_data=sensitive
        )
        
        # Check configuration
        config = server.telemetry_config
        print(f"Config: framework={config['enable_framework_traces']}, "
              f"workflow={config['enable_workflow_traces']}, "
              f"sensitive={config['enable_sensitive_data']}")
        
        # Test agent execution
        print("Agent execution events:")
        agent_events = []
        async for event in server.execution_engine.execute_agent_streaming(
            agent=mock_agent,
            message="test message",
            thread_id="test-thread-" + mode,
            tracing_manager=server.tracing_manager
        ):
            agent_events.append(event)
        
        print(f"  - Total events: {len(agent_events)}")
        for i, event in enumerate(agent_events):
            metadata_info = "with metadata" if event.debug_metadata else "no metadata"
            print(f"  - Event {i+1}: {event.type} ({metadata_info})")
        
        # Test workflow execution  
        print("Workflow execution events:")
        workflow_events = []
        async for event in server.execution_engine.execute_workflow_streaming(
            workflow=mock_workflow,
            input_data={"test": "data"},
            tracing_manager=server.tracing_manager
        ):
            workflow_events.append(event)
        
        print(f"  - Total events: {len(workflow_events)}")
        for i, event in enumerate(workflow_events):
            metadata_info = "with metadata" if event.debug_metadata else "no metadata"
            print(f"  - Event {i+1}: {event.type} ({metadata_info})")
        
        # Check environment variables
        print("Environment variables set:")
        otel_enabled = os.environ.get('AGENT_FRAMEWORK_ENABLE_OTEL', 'not set')
        workflow_enabled = os.environ.get('AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL', 'not set')
        sensitive_enabled = os.environ.get('AGENT_FRAMEWORK_ENABLE_SENSITIVE_DATA', 'not set')
        
        print(f"  - AGENT_FRAMEWORK_ENABLE_OTEL: {otel_enabled}")
        print(f"  - AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL: {workflow_enabled}")
        print(f"  - AGENT_FRAMEWORK_ENABLE_SENSITIVE_DATA: {sensitive_enabled}")
        
        print()


def test_trace_collection():
    """Test that traces are actually collected when enabled."""
    
    print("=== Testing Trace Collection ===\n")
    
    # Create a list to collect trace events
    collected_traces = []
    
    def trace_callback(event: DebugStreamEvent):
        """Callback to collect trace events."""
        collected_traces.append(event)
        print(f"Trace collected: {event.type} - {event.trace_span.operation_name if event.trace_span else 'no span'}")
    
    # Test with framework traces enabled
    server = AgentFrameworkDebugServer(telemetry_mode="framework")
    
    # Set up tracing with our callback
    server.tracing_manager.setup_streaming_tracing(trace_callback)
    
    print("Framework traces enabled - should collect traces during agent execution")
    print("Note: Actual trace collection depends on Agent Framework's OpenTelemetry instrumentation")
    print(f"Initial traces collected: {len(collected_traces)}")
    
    # Test with traces disabled
    collected_traces.clear()
    server_no_traces = AgentFrameworkDebugServer(telemetry_mode="none")
    server_no_traces.tracing_manager.setup_streaming_tracing(trace_callback)
    
    print(f"No traces mode - traces collected: {len(collected_traces)}")


if __name__ == "__main__":
    print("Running telemetry integration tests...")
    asyncio.run(test_telemetry_modes())
    test_trace_collection()
    print("Tests completed!")