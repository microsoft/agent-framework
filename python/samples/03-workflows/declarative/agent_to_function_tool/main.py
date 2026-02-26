# Copyright (c) Microsoft. All rights reserved.

"""Agent to Function Tool sample - demonstrates chaining agent output to function tools.

This sample shows how to:
1. Use InvokeAzureAgent to analyze user input with an AI model
2. Pass the agent's structured output to InvokeFunctionTool actions
3. Chain multiple function tools to process and transform data

The workflow:
1. Takes a user order request as input
2. Uses an Azure agent to extract structured order data (item, quantity, details)
3. Passes the extracted data to a function tool that calculates the order total
4. Uses another function tool to format the final confirmation message

Run with:
    python -m samples.03-workflows.declarative.agent_to_function_tool.main
"""

import asyncio
import os
from pathlib import Path
from typing import Any

from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.declarative import WorkflowFactory
from azure.identity import AzureCliCredential
from pydantic import BaseModel, Field

# Pricing data for the order calculation
ITEM_PRICES = {
    "pizza": {"small": 10.99, "medium": 14.99, "large": 18.99, "default": 14.99},
    "burger": {"small": 6.99, "medium": 8.99, "large": 10.99, "default": 8.99},
    "salad": {"small": 7.99, "medium": 9.99, "large": 11.99, "default": 9.99},
    "sandwich": {"small": 6.99, "medium": 8.99, "large": 10.99, "default": 8.99},
    "pasta": {"small": 11.99, "medium": 14.99, "large": 17.99, "default": 14.99},
}

EXTRAS_PRICES = {
    "extra cheese": 2.00,
    "bacon": 2.50,
    "avocado": 1.50,
    "mushrooms": 1.00,
    "pepperoni": 2.00,
}

# Agent instructions for order analysis
ORDER_ANALYSIS_INSTRUCTIONS = """You are an order analysis assistant. Analyze the customer's order request and extract:
- item: what they want to order (e.g., "pizza", "burger", "salad")
- quantity: how many (as a number, default to 1 if not specified)
- details: any special requests, modifications, or size (e.g., "large", "extra cheese")
- delivery_address: where to deliver (if mentioned, otherwise empty string)

Always respond with valid JSON matching the required format."""


# Pydantic model for structured agent output
class OrderAnalysis(BaseModel):
    """Structured output from the order analysis agent."""

    item: str = Field(description="The food item being ordered (e.g., pizza, burger)")
    quantity: int = Field(description="Number of items ordered", default=1)
    details: str = Field(description="Special requests, size, or modifications")
    delivery_address: str = Field(description="Delivery address if provided, empty string otherwise", default="")


def calculate_order_total(order_data: dict[str, Any]) -> dict[str, Any]:
    """Calculate the total cost of an order based on the agent's structured analysis.

    Args:
        order_data: Structured dict from the agent containing order analysis.

    Returns:
        Dictionary with pricing breakdown.
    """
    # Handle case where order_data might be None or invalid
    if not order_data or not isinstance(order_data, dict):
        return {
            "error": f"Invalid order data: {order_data}",
            "subtotal": 0.0,
            "tax": 0.0,
            "delivery_fee": 0.0,
            "total": 0.0,
        }

    item = str(order_data.get("item", "")).lower()
    quantity = int(order_data.get("quantity", 1))
    details = str(order_data.get("details", "")).lower()
    has_delivery = bool(order_data.get("delivery_address"))

    # Determine size from details
    size = "default"
    for s in ["small", "medium", "large"]:
        if s in details:
            size = s
            break

    # Get base price for item
    item_key = None
    for key in ITEM_PRICES:
        if key in item:
            item_key = key
            break

    unit_price = ITEM_PRICES[item_key].get(size, ITEM_PRICES[item_key]["default"]) if item_key else 12.99

    # Calculate extras
    extras_total = 0.0
    applied_extras: list[dict[str, Any]] = []
    for extra, price in EXTRAS_PRICES.items():
        if extra in details:
            extras_total += price * quantity
            applied_extras.append({"name": extra, "price": price})

    # Calculate totals
    subtotal = (unit_price * quantity) + extras_total
    tax = round(subtotal * 0.08, 2)  # 8% tax
    delivery_fee = 5.00 if has_delivery else 0.0
    total = round(subtotal + tax + delivery_fee, 2)

    return {
        "item": item,
        "quantity": quantity,
        "size": size if size != "default" else "regular",
        "unit_price": unit_price,
        "extras": applied_extras,
        "extras_total": extras_total,
        "subtotal": round(subtotal, 2),
        "tax": tax,
        "delivery_fee": delivery_fee,
        "total": total,
        "has_delivery": has_delivery,
    }


def format_order_confirmation(order_data: dict[str, Any], order_calculation: dict[str, Any]) -> str:
    """Format a human-readable order confirmation message.

    Args:
        order_data: Structured dict from the agent with order details.
        order_calculation: Pricing calculation from calculate_order_total.

    Returns:
        Formatted confirmation message.
    """
    calc = order_calculation

    # Handle error case
    if "error" in calc:
        return f"Sorry, we couldn't process your order: {calc['error']}"

    # Build the confirmation message
    qty = int(calc.get("quantity", 1))
    size = calc.get("size", "regular").title()
    item = calc.get("item", "item").title()
    lines = [
        "=" * 50,
        "ORDER CONFIRMATION",
        "=" * 50,
        "",
        f"Item: {qty}x {size} {item}",
        f"Unit Price: ${calc.get('unit_price', 0):.2f}",
    ]

    # Add extras if any
    extras = calc.get("extras", [])
    if extras:
        lines.append("\nExtras:")
        for extra in extras:
            lines.append(f"  + {extra['name'].title()}: ${extra['price']:.2f} each")
        lines.append(f"  Extras Total: ${calc.get('extras_total', 0):.2f}")

    lines.extend([
        "",
        "-" * 30,
        f"Subtotal: ${calc.get('subtotal', 0):.2f}",
        f"Tax (8%): ${calc.get('tax', 0):.2f}",
    ])

    if calc.get("has_delivery"):
        delivery_address = order_data.get("delivery_address", "Address provided") if order_data else "Address provided"
        lines.extend([
            f"Delivery Fee: ${calc.get('delivery_fee', 0):.2f}",
            f"Delivery To: {delivery_address}",
        ])

    lines.extend([
        "-" * 30,
        f"TOTAL: ${calc.get('total', 0):.2f}",
        "=" * 50,
        "",
        "Thank you for your order!",
    ])

    return "\n".join(lines)


async def main():
    """Run the agent to function tool workflow."""
    # Create Azure OpenAI Responses client
    chat_client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    # Create the order analysis agent with structured output
    order_analysis_agent = chat_client.as_agent(
        name="OrderAnalysisAgent",
        instructions=ORDER_ANALYSIS_INSTRUCTIONS,
        default_options={"response_format": OrderAnalysis},
    )

    # Agent registry
    agents = {
        "OrderAnalysisAgent": order_analysis_agent,
    }

    # Get the path to the workflow YAML file
    workflow_path = Path(__file__).parent / "workflow.yaml"

    # Create the workflow factory with agents and tools
    factory = (
        WorkflowFactory(agents=agents)
        .register_tool("calculate_order_total", calculate_order_total)
        .register_tool("format_order_confirmation", format_order_confirmation)
    )

    # Create the workflow from the YAML definition
    workflow = factory.create_workflow_from_yaml_path(workflow_path)

    print("=" * 60)
    print("Agent to Function Tool Workflow Demo")
    print("=" * 60)
    print()
    print("This workflow demonstrates:")
    print("  1. Using InvokeAzureAgent to analyze user input")
    print("  2. Passing agent's structured output to InvokeFunctionTool")
    print("  3. Chaining multiple function tools together")
    print()

    # Test with different order inputs
    test_queries = [
        "I want to order 3 large pizzas with extra cheese for delivery to 123 Main St",
        "2 medium burgers with bacon please",
        "Can I get a small salad with avocado and mushrooms, pick up",
    ]

    for query in test_queries:
        print("-" * 60)
        print(f"Input: {query}")
        print("-" * 60)

        # Run the workflow with streaming to capture output
        try:
            async for event in workflow.run(query, stream=True):
                if event.type == "output" and isinstance(event.data, str):
                    print(event.data, end="", flush=True)
        except Exception as e:
            print(f"\nWorkflow error: {type(e).__name__}: {e}")

        print("\n")


if __name__ == "__main__":
    asyncio.run(main())
