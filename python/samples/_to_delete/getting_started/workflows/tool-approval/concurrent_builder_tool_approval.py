# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import AsyncIterable
from typing import Annotated

from agent_framework import (
    ChatMessage,
    Content,
    WorkflowEvent,
    tool,
)
from agent_framework.openai import OpenAIChatClient
from agent_framework.orchestrations import ConcurrentBuilder

"""
Sample: Concurrent Workflow with Tool Approval Requests

This sample demonstrates how to use ConcurrentBuilder with tools that require human
approval before execution. Multiple agents run in parallel, and any tool requiring
approval will pause the workflow until the human responds.

This sample works as follows:
1. A ConcurrentBuilder workflow is created with two agents running in parallel.
2. Both agents have the same tools, including one requiring approval (execute_trade).
3. Both agents receive the same task and work concurrently on their respective stocks.
4. When either agent tries to execute a trade, it triggers an approval request.
5. The sample simulates human approval and the workflow completes.
6. Results from both agents are aggregated and output.

Purpose:
Show how tool call approvals work in parallel execution scenarios where multiple
agents may independently trigger approval requests.

Demonstrate:
- Handling multiple approval requests from different agents in concurrent workflows.
- Handling  during concurrent agent execution.
- Understanding that approval pauses only the agent that triggered it, not all agents.

Prerequisites:
- OpenAI or Azure OpenAI configured with the required environment variables.
- Basic familiarity with ConcurrentBuilder and streaming workflow events.
"""


# 1. Define market data tools (no approval required)
# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# See:
# samples/getting_started/tools/function_tool_with_approval.py
# samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_stock_price(symbol: Annotated[str, "The stock ticker symbol"]) -> str:
    """Get the current stock price for a given symbol."""
    # Mock data for demonstration
    prices = {"AAPL": 175.50, "GOOGL": 140.25, "MSFT": 378.90, "AMZN": 178.75}
    price = prices.get(symbol.upper(), 100.00)
    return f"{symbol.upper()}: ${price:.2f}"


@tool(approval_mode="never_require")
def get_market_sentiment(symbol: Annotated[str, "The stock ticker symbol"]) -> str:
    """Get market sentiment analysis for a stock."""
    # Mock sentiment data
    mock_data = {
        "AAPL": "Market sentiment for AAPL: Bullish (68% positive mentions in last 24h)",
        "GOOGL": "Market sentiment for GOOGL: Neutral (50% positive mentions in last 24h)",
        "MSFT": "Market sentiment for MSFT: Bullish (72% positive mentions in last 24h)",
        "AMZN": "Market sentiment for AMZN: Bearish (40% positive mentions in last 24h)",
    }
    return mock_data.get(symbol.upper(), f"Market sentiment for {symbol.upper()}: Unknown")


# 2. Define trading tools (approval required)
@tool(approval_mode="always_require")
def execute_trade(
    symbol: Annotated[str, "The stock ticker symbol"],
    action: Annotated[str, "Either 'buy' or 'sell'"],
    quantity: Annotated[int, "Number of shares to trade"],
) -> str:
    """Execute a stock trade. Requires human approval due to financial impact."""
    return f"Trade executed: {action.upper()} {quantity} shares of {symbol.upper()}"


@tool(approval_mode="never_require")
def get_portfolio_balance() -> str:
    """Get current portfolio balance and available funds."""
    return "Portfolio: $50,000 invested, $10,000 cash available. Holdings: AAPL, GOOGL, MSFT."


def _print_output(event: WorkflowEvent) -> None:
    if not event.data:
        raise ValueError("WorkflowEvent has no data")

    if not isinstance(event.data, list) and not all(isinstance(msg, ChatMessage) for msg in event.data):
        raise ValueError("WorkflowEvent data is not a list of ChatMessage")

    messages: list[ChatMessage] = event.data  # type: ignore

    print("\n" + "-" * 60)
    print("Workflow completed. Aggregated results from both agents:")
    for msg in messages:
        if msg.text:
            print(f"- {msg.author_name or msg.role}: {msg.text}")


async def process_event_stream(stream: AsyncIterable[WorkflowEvent]) -> dict[str, Content] | None:
    """Process events from the workflow stream to capture human feedback requests."""
    requests: dict[str, Content] = {}
    async for event in stream:
        if event.type == "request_info" and isinstance(event.data, Content):
            # We are only expecting tool approval requests in this sample
            requests[event.request_id] = event.data
        elif event.type == "output":
            _print_output(event)

    responses: dict[str, Content] = {}
    if requests:
        for request_id, request in requests.items():
            if request.type == "function_approval_request":
                print(f"\nSimulating human approval for: {request.function_call.name}")  # type: ignore
                # Create approval response
                responses[request_id] = request.to_function_approval_response(approved=True)

    return responses if responses else None


async def main() -> None:
    # 3. Create two agents focused on different stocks but with the same tool sets
    chat_client = OpenAIChatClient()

    microsoft_agent = chat_client.as_agent(
        name="MicrosoftAgent",
        instructions=(
            "You are a personal trading assistant focused on Microsoft (MSFT). "
            "You manage my portfolio and take actions based on market data."
        ),
        tools=[get_stock_price, get_market_sentiment, get_portfolio_balance, execute_trade],
    )

    google_agent = chat_client.as_agent(
        name="GoogleAgent",
        instructions=(
            "You are a personal trading assistant focused on Google (GOOGL). "
            "You manage my trades and portfolio based on market conditions."
        ),
        tools=[get_stock_price, get_market_sentiment, get_portfolio_balance, execute_trade],
    )

    # 4. Build a concurrent workflow with both agents
    # ConcurrentBuilder requires at least 2 participants for fan-out
    workflow = ConcurrentBuilder(participants=[microsoft_agent, google_agent]).build()

    # 5. Start the workflow - both agents will process the same task in parallel
    print("Starting concurrent workflow with tool approval...")
    print("-" * 60)

    # Initiate the first run of the workflow.
    # Runs are not isolated; state is preserved across multiple calls to run.
    stream = workflow.run(
        "Manage my portfolio. Use a max of 5000 dollars to adjust my position using "
        "your best judgment based on market sentiment. No need to confirm trades with me.",
        stream=True,
    )

    pending_responses = await process_event_stream(stream)
    while pending_responses is not None:
        # Run the workflow until there is no more human feedback to provide,
        # in which case this workflow completes.
        stream = workflow.run(stream=True, responses=pending_responses)
        pending_responses = await process_event_stream(stream)

    """
    Sample Output:
    Starting concurrent workflow with tool approval...
    ------------------------------------------------------------

    Approval requested for tool: execute_trade
    Arguments: {"symbol":"MSFT","action":"buy","quantity":13}

    Approval requested for tool: execute_trade
    Arguments: {"symbol":"GOOGL","action":"buy","quantity":35}

    Simulating human approval for: execute_trade

    Simulating human approval for: execute_trade

    ------------------------------------------------------------
    Workflow completed. Aggregated results from both agents:
    - user: Manage my portfolio. Use a max of 5000 dollars to adjust my position using your best judgment based on
            market sentiment. No need to confirm trades with me.
    - MicrosoftAgent: I have successfully executed the trade, purchasing 13 shares of Microsoft (MSFT). This action
                      was based on the positive market sentiment and available funds within the specified limit.
                      Your portfolio has been adjusted accordingly.
    - GoogleAgent: I have successfully executed the trade, purchasing 35 shares of GOOGL. If you need further
                   assistance or any adjustments, feel free to ask!
    """


if __name__ == "__main__":
    asyncio.run(main())
