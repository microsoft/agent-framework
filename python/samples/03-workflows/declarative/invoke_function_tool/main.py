# Copyright (c) Microsoft. All rights reserved.

"""Invoke Function Tool sample - demonstrates InvokeFunctionTool workflow actions.

This sample shows how to:
1. Define Python functions that can be called from workflows
2. Register functions with WorkflowFactory.register_tool()
3. Use the InvokeFunctionTool action in YAML to invoke registered functions
4. Pass arguments using expression syntax (=Local.variable)
5. Capture function output in workflow variables

Run with:
    python -m samples.03-workflows.declarative.invoke_function_tool.main
"""

import asyncio
from pathlib import Path
from typing import Any

from agent_framework.declarative import WorkflowFactory


# Define the function tools that will be registered with the workflow
def get_weather(location: str, unit: str = "F") -> dict[str, Any]:
    """Get weather information for a location.

    This is a mock function that returns simulated weather data.
    In a real application, this would call a weather API.

    Args:
        location: The city or location to get weather for.
        unit: Temperature unit ("F" for Fahrenheit, "C" for Celsius).

    Returns:
        Dictionary with weather information.
    """
    # Simulated weather data
    weather_data = {
        "Seattle": {"temp": 55, "condition": "rainy"},
        "New York": {"temp": 70, "condition": "partly cloudy"},
        "Los Angeles": {"temp": 85, "condition": "sunny"},
        "Chicago": {"temp": 60, "condition": "windy"},
    }

    data = weather_data.get(location, {"temp": 72, "condition": "unknown"})

    # Convert to Celsius if requested
    temp = data["temp"]
    if unit.upper() == "C":
        temp = round((temp - 32) * 5 / 9)  # type: ignore

    return {
        "location": location,
        "temp": temp,
        "unit": unit.upper(),
        "condition": data["condition"],
    }


def format_message(template: str, data: dict[str, Any]) -> str:
    """Format a message template with data.

    Args:
        template: A string template with {key} placeholders.
        data: Dictionary of values to substitute.

    Returns:
        Formatted message string.
    """
    try:
        return template.format(**data)
    except KeyError as e:
        return f"Error formatting message: missing key {e}"


async def main():
    """Run the invoke function tool workflow."""
    # Get the path to the workflow YAML file
    workflow_path = Path(__file__).parent / "workflow.yaml"

    # Create the workflow factory and register our tool functions
    factory = (
        WorkflowFactory().register_tool("get_weather", get_weather).register_tool("format_message", format_message)
    )

    # Create the workflow from the YAML definition
    workflow = factory.create_workflow_from_yaml_path(workflow_path)

    print("=" * 60)
    print("Invoke Function Tool Workflow Demo")
    print("=" * 60)

    # Test with different inputs - both location and unit must be provided
    # as the workflow expects them in Workflow.Inputs
    test_inputs = [
        {"location": "Seattle", "unit": "F"},
        {"location": "New York", "unit": "C"},
        {"location": "Los Angeles", "unit": "F"},
        {"location": "Chicago", "unit": "C"},
    ]

    for inputs in test_inputs:
        print(f"\nInput: {inputs}")
        print("-" * 40)

        # Run the workflow
        events = await workflow.run(inputs)

        # Get the outputs
        outputs = events.get_outputs()
        for output in outputs:
            print(f"Output: {output}")


if __name__ == "__main__":
    asyncio.run(main())
