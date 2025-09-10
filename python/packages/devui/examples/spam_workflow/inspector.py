#!/usr/bin/env python3
"""Workflow Event Inspector

This inspector runs a workflow and captures all events emitted by the execution engine,
then dumps them to a JSON file for debugging UI behavior and data assumptions.

Usage:
    python inspector.py [input_message] [--output output.json]
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Import the sample workflows
from .workflow import workflow as simple_workflow

# Import the execution engine and workflow
from agent_framework_devui._execution import ExecutionEngine
from agent_framework_devui._models import DebugStreamEvent


class WorkflowInspector:
    """Inspector that captures and analyzes workflow execution events."""

    def __init__(self):
        self.execution_engine = ExecutionEngine()
        self.events: List[Dict[str, Any]] = []

    async def run_and_capture(
        self, workflow, input_message: str, workflow_name: str = "workflow"
    ) -> List[Dict[str, Any]]:
        """Run workflow and capture all events."""
        print(f"🔍 Inspecting {workflow_name} execution for input: '{input_message}'")

        self.events.clear()

        try:
            async for debug_event in self.execution_engine.execute_workflow_streaming(
                workflow=workflow, input_data=input_message
            ):
                # Convert DebugStreamEvent to serializable format
                event_data = self._serialize_debug_event(debug_event)
                self.events.append(event_data)

                # Print real-time feedback
                print(f"📡 Event: {debug_event.type}")
                if hasattr(debug_event, "event") and debug_event.event:
                    # Handle both WorkflowEvent objects and serialized dicts
                    if isinstance(debug_event.event, dict):
                        event_type = debug_event.event.get("type", "unknown")
                        executor_id = debug_event.event.get("executor_id", "unknown")
                    else:
                        # WorkflowEvent object
                        event_type = debug_event.event.__class__.__name__
                        executor_id = getattr(debug_event.event, "executor_id", "unknown")
                    print(f"   └── {event_type} from {executor_id}")

        except Exception as e:
            print(f"❌ Error during execution: {e}")
            # Add error event
            error_event = {"type": "inspector_error", "error": str(e), "timestamp": datetime.now().isoformat()}
            self.events.append(error_event)

        print(f"✅ Captured {len(self.events)} events")
        return self.events

    def _serialize_debug_event(self, debug_event: DebugStreamEvent) -> Dict[str, Any]:
        """Convert DebugStreamEvent to serializable dictionary."""
        event_data: Dict[str, Any] = {
            "type": debug_event.type,
            "timestamp": debug_event.timestamp,
        }

        # Add optional fields if present
        if debug_event.thread_id:
            event_data["thread_id"] = debug_event.thread_id

        if debug_event.error:
            event_data["error"] = debug_event.error

        if debug_event.debug_metadata:
            event_data["debug_metadata"] = debug_event.debug_metadata

        # Handle workflow-specific data
        if debug_event.workflow_dump:
            event_data["workflow_dump"] = debug_event.workflow_dump

        if debug_event.mermaid_diagram:
            event_data["mermaid_diagram"] = debug_event.mermaid_diagram

        # Handle events (workflow events)
        if debug_event.event:
            if isinstance(debug_event.event, dict):
                # Already serialized
                event_data["event"] = debug_event.event
            else:
                # WorkflowEvent object - convert to serializable format
                event_data["event"] = {
                    "type": debug_event.event.__class__.__name__,
                    "data": getattr(debug_event.event, "data", None),
                    "executor_id": getattr(debug_event.event, "executor_id", None),
                }

        # Handle agent updates (not used in workflow but included for completeness)
        if debug_event.update:
            try:
                # Try to serialize the update object
                if hasattr(debug_event.update, "model_dump"):
                    event_data["update"] = debug_event.update.model_dump()
                elif hasattr(debug_event.update, "dict"):
                    event_data["update"] = debug_event.update.dict()
                else:
                    event_data["update"] = str(debug_event.update)
            except Exception as e:
                event_data["update"] = f"Serialization error: {e!s}"

        # Handle trace spans
        if debug_event.trace_span:
            try:
                if hasattr(debug_event.trace_span, "model_dump"):
                    event_data["trace_span"] = debug_event.trace_span.model_dump()
                elif hasattr(debug_event.trace_span, "dict"):
                    event_data["trace_span"] = debug_event.trace_span.dict()
                else:
                    event_data["trace_span"] = str(debug_event.trace_span)
            except Exception as e:
                event_data["trace_span"] = f"Serialization error: {e!s}"

        return event_data

    def save_to_file(self, output_path: str, workflow_name: str = "workflow", include_summary: bool = True) -> None:
        """Save captured events to JSON file with optional summary."""
        output_data = {
            "metadata": {
                "inspector_version": "1.0.0",
                "timestamp": datetime.now().isoformat(),
                "total_events": len(self.events),
                "workflow_name": workflow_name,
            },
            "events": self.events,
        }

        if include_summary:
            output_data["summary"] = self._generate_summary()

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"💾 Events saved to: {output_path}")

    def _generate_summary(self) -> Dict[str, Any]:
        """Generate a summary of captured events for easy debugging."""
        event_types = {}
        executors_seen = set()
        workflow_events = []

        for event in self.events:
            event_type = event.get("type", "unknown")
            event_types[event_type] = event_types.get(event_type, 0) + 1

            # Track workflow events specifically
            if event_type == "workflow_event" and "event" in event:
                workflow_event = event["event"]
                workflow_events.append({
                    "event_type": workflow_event.get("type", "unknown"),
                    "executor_id": workflow_event.get("executor_id", "unknown"),
                    "timestamp": event.get("timestamp"),
                })

                if "executor_id" in workflow_event:
                    executors_seen.add(workflow_event["executor_id"])

        return {
            "event_type_counts": event_types,
            "unique_executors": list(executors_seen),
            "workflow_event_sequence": workflow_events,
            "execution_flow": [f"{we['executor_id']}: {we['event_type']}" for we in workflow_events],
        }

    def print_summary(self) -> None:
        """Print a human-readable summary to console."""
        summary = self._generate_summary()

        print("\n📊 EXECUTION SUMMARY")
        print("=" * 50)
        print(f"Total Events: {len(self.events)}")

        print("\nEvent Types:")
        for event_type, count in summary["event_type_counts"].items():
            print(f"  • {event_type}: {count}")

        print("\nExecutors Involved:")
        for executor in summary["unique_executors"]:
            print(f"  • {executor}")

        print("\nExecution Flow:")
        for i, flow_item in enumerate(summary["execution_flow"], 1):
            print(f"  {i}. {flow_item}")


async def main():
    """Main function to run the inspector."""
    # Parse command line arguments
    input_message = sys.argv[1] if len(sys.argv) > 1 else None
    workflow_type = sys.argv[2] if len(sys.argv) > 2 else "both"

    # Test cases for different scenarios
    test_cases = [
        ("Hello, how are you today?", "normal_legitimate"),
        ("This is a spam advertisement for you!", "spam_message"),
        ("URGENT: This is important! Please review asap", "high_priority"),
        ("FREE PRIZE! You won $1000000!", "scam_spam"),
        ("Check out this amazing offer!", "commercial_spam"),
    ]

    # If specific input provided, use it
    if input_message:
        test_cases = [(input_message, "custom_input")]

    # Run the inspector
    inspector = WorkflowInspector()

    print("🚀 Starting Workflow Inspector")
    print("=" * 60)

    # Test workflows based on type parameter
    workflows_to_test = []
    if workflow_type in ["simple", "both"]:
        workflows_to_test.append((simple_workflow, "simple_workflow"))

    # Run tests for each workflow and test case
    script_dir = Path(__file__).parent
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for workflow, workflow_name in workflows_to_test:
        print(f"\n📊 Testing {workflow_name.upper()}")
        print("-" * 60)

        for test_input, case_name in test_cases:
            print(f"\n🧪 Test Case: {case_name}")
            print(f"Input: '{test_input}'")
            print("-" * 40)

            # Capture events
            await inspector.run_and_capture(workflow, test_input, workflow_name)

            # Generate output filename
            output_file = script_dir / f"{workflow_name}_{case_name}_{timestamp}.json"

            # Print summary
            inspector.print_summary()

            # Save to file
            inspector.save_to_file(str(output_file), workflow_name, include_summary=True)

            print(f"📄 Events saved to: {output_file.name}")

            # Add delay between tests to make timing more visible
            print("⏱️  Waiting 2 seconds before next test...")
            await asyncio.sleep(2)

    print("\n🎉 Inspection complete! Check the generated JSON files for detailed event data.")
    print("💡 Usage: python inspector.py [input_message] [workflow_type]")
    print("   - workflow_type: 'simple', 'complex', or 'both' (default: 'both')")


if __name__ == "__main__":
    asyncio.run(main())
