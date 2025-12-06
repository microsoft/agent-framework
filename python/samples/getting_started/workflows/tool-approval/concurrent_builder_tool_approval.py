# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import (
    ChatMessage,
    ConcurrentBuilder,
    FunctionApprovalRequestContent,
    FunctionApprovalResponseContent,
    RequestInfoEvent,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
    ai_function,
)
from agent_framework.openai import OpenAIChatClient

"""
Sample: Concurrent Workflow with Tool Approval Requests

This sample demonstrates how to use ConcurrentBuilder with tools that require human
approval before execution. Multiple agents run in parallel, and any tool requiring
approval will pause the workflow until the human responds.

This sample works as follows:
1. A ConcurrentBuilder workflow is created with two agents running in parallel.
2. One agent has a tool requiring approval (financial transaction).
3. The other agent has only non-approval tools (market data lookup).
4. Both agents receive the same task and work concurrently.
5. When the financial agent tries to execute a trade, it triggers an approval request.
6. The sample simulates human approval and the workflow completes.
7. Results from both agents are aggregated and output.

Purpose:
Show how tool call approvals work in parallel execution scenarios where only some
agents have sensitive tools.

Demonstrate:
- Combining agents with and without approval-required tools in concurrent workflows.
- Handling RequestInfoEvent during concurrent agent execution.
- Understanding that approval pauses only the agent that triggered it, not all agents.

Prerequisites:
- OpenAI or Azure OpenAI configured with the required environment variables.
- Basic familiarity with ConcurrentBuilder and streaming workflow events.
"""


# 1. Define tools for the research agent (no approval required)
@ai_function
def get_stock_price(symbol: Annotated[str, "The stock ticker symbol"]) -> str:
    """Get the current stock price for a given symbol."""
    # Mock data for demonstration
    prices = {"AAPL": 175.50, "GOOGL": 140.25, "MSFT": 378.90, "AMZN": 178.75}
    price = prices.get(symbol.upper(), 100.00)
    return f"{symbol.upper()}: ${price:.2f}"


@ai_function
def get_market_sentiment(symbol: Annotated[str, "The stock ticker symbol"]) -> str:
    """Get market sentiment analysis for a stock."""
    # Mock sentiment data
    return f"Market sentiment for {symbol.upper()}: Bullish (72% positive mentions in last 24h)"


# 2. Define tools for the trading agent (approval required for trades)
@ai_function(approval_mode="always_require")
def execute_trade(
    symbol: Annotated[str, "The stock ticker symbol"],
    action: Annotated[str, "Either 'buy' or 'sell'"],
    quantity: Annotated[int, "Number of shares to trade"],
) -> str:
    """Execute a stock trade. Requires human approval due to financial impact."""
    return f"Trade executed: {action.upper()} {quantity} shares of {symbol.upper()}"


@ai_function
def get_portfolio_balance() -> str:
    """Get current portfolio balance and available funds."""
    return "Portfolio: $50,000 invested, $10,000 cash available"


async def main() -> None:
    # 3. Create two agents with different tool sets
    chat_client = OpenAIChatClient()

    research_agent = chat_client.create_agent(
        name="ResearchAgent",
        instructions=(
            "You are a market research analyst. Analyze stock data and provide "
            "recommendations based on price and sentiment. Do not execute trades."
        ),
        tools=[get_stock_price, get_market_sentiment],
    )

    trading_agent = chat_client.create_agent(
        name="TradingAgent",
        instructions=(
            "You are a trading assistant. When asked to buy or sell shares, you MUST "
            "call the execute_trade function to complete the transaction. Check portfolio "
            "balance first, then execute the requested trade."
        ),
        tools=[get_portfolio_balance, execute_trade],
    )

    # 4. Build a concurrent workflow with both agents
    # ConcurrentBuilder requires at least 2 participants for fan-out
    workflow = ConcurrentBuilder().participants([research_agent, trading_agent]).build()

    # 5. Start the workflow - both agents will process the same task in parallel
    print("Starting concurrent workflow with tool approval...")
    print("Two agents will analyze MSFT - one for research, one for trading.")
    print("-" * 60)

    # Phase 1: Run workflow and collect all events (stream ends at IDLE or IDLE_WITH_PENDING_REQUESTS)
    request_info_events: list[RequestInfoEvent] = []
    workflow_completed_without_approvals = False
    async for event in workflow.run_stream("Analyze MSFT stock and if sentiment is positive, buy 10 shares."):
        if isinstance(event, RequestInfoEvent):
            request_info_events.append(event)
            if isinstance(event.data, FunctionApprovalRequestContent):
                print(f"\nApproval requested for tool: {event.data.function_call.name}")
                print(f"  Arguments: {event.data.function_call.arguments}")
        elif isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
            workflow_completed_without_approvals = True

    # 6. Handle approval requests (if any)
    if request_info_events:
        responses: dict[str, FunctionApprovalResponseContent] = {}
        for request_event in request_info_events:
            if isinstance(request_event.data, FunctionApprovalRequestContent):
                print(f"\nSimulating human approval for: {request_event.data.function_call.name}")
                # Create approval response
                responses[request_event.request_id] = request_event.data.create_response(approved=True)

        if responses:
            # Phase 2: Send all approvals and continue workflow
            output: list[ChatMessage] | None = None
            async for event in workflow.send_responses_streaming(responses):
                if isinstance(event, WorkflowOutputEvent):
                    output = event.data

            if output:
                print("\n" + "-" * 60)
                print("Workflow completed. Aggregated results from both agents:")
                for msg in output:
                    if hasattr(msg, "author_name") and msg.author_name:
                        print(f"\n[{msg.author_name}]:")
                    text = msg.text[:300] + "..." if len(msg.text) > 300 else msg.text
                    if text:
                        print(f"  {text}")
    elif workflow_completed_without_approvals:
        print("\nWorkflow completed without requiring approvals.")
        print("(The trading agent may have only checked balance without executing a trade)")

    """
    Sample Output:
    Starting concurrent workflow with tool approval...
    Two agents will analyze MSFT - one for research, one for trading.
    ------------------------------------------------------------

    Approval requested for tool: execute_trade
      Arguments: {"symbol": "MSFT", "action": "buy", "quantity": 10}
    Simulating human approval for: execute_trade

    ------------------------------------------------------------
    Workflow completed. Aggregated results from both agents:

    [ResearchAgent]:
      MSFT is currently trading at $175.50 with bullish market sentiment
      (72% positive mentions). Based on the positive sentiment, this could
      be a good opportunity to consider buying.

    [TradingAgent]:
      I've checked your portfolio balance ($10,000 cash available) and
      executed the trade: BUY 10 shares of MSFT at approximately $175.50
      per share, totaling ~$1,755.
    """


if __name__ == "__main__":
    asyncio.run(main())
