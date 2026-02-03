# Copyright (c) Microsoft. All rights reserved.

"""
Multi-Agent Travel Planning Workflow Evaluation with Multiple Response Tracking

This sample demonstrates a multi-agent travel planning workflow using the Azure AI Client that:
1. Processes travel queries through 7 specialized agents
2. Tracks MULTIPLE response and conversation IDs per agent for evaluation
3. Uses the new Prompt Agents API (V2)
4. Captures complete interaction sequences including multiple invocations
5. Aggregates findings through a travel planning coordinator

WORKFLOW STRUCTURE (7 agents):
- Travel Agent Executor → Hotel Search, Flight Search, Activity Search (fan-out)
- Hotel Search Executor → Booking Information Aggregation Executor
- Flight Search Executor → Booking Information Aggregation Executor
- Booking Information Aggregation Executor → Booking Confirmation Executor
- Booking Confirmation Executor → Booking Payment Executor
- Booking Information Aggregation, Booking Payment, Activity Search → Travel Planning Coordinator (ResearchLead) for final aggregation (fan-in)

Agents:
1. Travel Agent - Main coordinator (no tools to avoid thread conflicts)
2. Hotel Search - Searches hotels with tools
3. Flight Search - Searches flights with tools
4. Activity Search - Searches activities with tools
5. Booking Information Aggregation - Aggregates hotel & flight booking info
6. Booking Confirmation - Confirms bookings with tools
7. Booking Payment - Processes payments with tools
"""

import asyncio
import os
from collections import defaultdict

from _tools import (
    check_flight_availability,
    check_hotel_availability,
    confirm_booking,
    get_flight_details,
    get_hotel_details,
    process_payment,
    search_activities,
    search_flights,
    # Travel planning tools
    search_hotels,
    validate_payment_method,
)
from agent_framework import (
    AgentExecutorResponse,
    AgentResponseUpdate,
    AgentRunUpdateEvent,
    ChatMessage,
    Executor,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    executor,
    handler,
    tool,
)
from agent_framework.azure import AzureAIClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv
from typing_extensions import Never

load_dotenv()


@executor(id="start_executor")
async def start_executor(input: str, ctx: WorkflowContext[list[ChatMessage]]) -> None:
    """Initiates the workflow by sending the user query to all specialized agents."""
    await ctx.send_message([ChatMessage(role="user", text=input)])


class ResearchLead(Executor):
    """Aggregates and summarizes travel planning findings from all specialized agents."""

    def __init__(self, chat_client: AzureAIClient, id: str = "travel-planning-coordinator"):
        # store=True to preserve conversation history for evaluation
        self.agent = chat_client.as_agent(
            id="travel-planning-coordinator",
            instructions=(
                "You are the final coordinator. You will receive responses from multiple agents: "
                "booking-info-aggregation-agent (hotel/flight options), booking-payment-agent (payment confirmation), "
                "and activity-search-agent (activities). "
                "Review each agent's response, then create a comprehensive travel itinerary organized by: "
                "1. Flights 2. Hotels 3. Activities 4. Booking confirmations 5. Payment details. "
                "Clearly indicate which information came from which agent. Do not use tools."
            ),
            name="travel-planning-coordinator",
            store=True,
        )
        super().__init__(id=id)

    @handler
    async def fan_in_handle(self, responses: list[AgentExecutorResponse], ctx: WorkflowContext[Never, str]) -> None:
        user_query = responses[0].full_conversation[0].text

        # Extract findings from all agent responses
        agent_findings = self._extract_agent_findings(responses)
        summary_text = (
            "\n".join(agent_findings) if agent_findings else "No specific findings were provided by the agents."
        )

        # Generate comprehensive travel plan summary
        messages = [
            ChatMessage(
                role=Role.SYSTEM,
                text="You are a travel planning coordinator. Summarize findings from multiple specialized travel agents and provide a clear, comprehensive travel plan based on the user's query.",
            ),
            ChatMessage(
                role=Role.USER,
                text=f"Original query: {user_query}\n\nFindings from specialized travel agents:\n{summary_text}\n\nPlease provide a comprehensive travel plan based on these findings.",
            ),
        ]

        try:
            final_response = await self.agent.run(messages)
            output_text = (
                final_response.messages[-1].text
                if final_response.messages and final_response.messages[-1].text
                else f"Based on the available findings, here's your travel plan for '{user_query}': {summary_text}"
            )
        except Exception:
            output_text = f"Based on the available findings, here's your travel plan for '{user_query}': {summary_text}"

        await ctx.yield_output(output_text)

    def _extract_agent_findings(self, responses: list[AgentExecutorResponse]) -> list[str]:
        """Extract findings from agent responses."""
        agent_findings = []

        for response in responses:
            findings = []
            if response.agent_response and response.agent_response.messages:
                for msg in response.agent_response.messages:
                    if msg.role == Role.ASSISTANT and msg.text and msg.text.strip():
                        findings.append(msg.text.strip())

            if findings:
                combined_findings = " ".join(findings)
                agent_findings.append(f"[{response.executor_id}]: {combined_findings}")

        return agent_findings


async def run_workflow_with_response_tracking(query: str, chat_client: AzureAIClient | None = None) -> dict:
    """Run multi-agent workflow and track conversation IDs, response IDs, and interaction sequence.

    Args:
        query: The user query to process through the multi-agent workflow
        chat_client: Optional AzureAIClient instance

    Returns:
        Dictionary containing interaction sequence, conversation/response IDs, and conversation analysis
    """
    if chat_client is None:
        try:
            # Create AIProjectClient with the correct API version for V2 prompt agents
            project_client = AIProjectClient(
                endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
                credential=credential,
                api_version="2025-11-15-preview",
            )

            async with (
                DefaultAzureCredential() as credential,
                project_client,
                AzureAIClient(project_client=project_client, credential=credential) as client,
            ):
                return await _run_workflow_with_client(query, client)
        except Exception as e:
            print(f"Error during workflow execution: {e}")
            raise
    else:
        return await _run_workflow_with_client(query, chat_client)


async def _run_workflow_with_client(query: str, chat_client: AzureAIClient) -> dict:
    """Execute workflow with given client and track all interactions."""

    # Initialize tracking variables - use lists to track multiple responses per agent
    conversation_ids = defaultdict(list)
    response_ids = defaultdict(list)
    workflow_output = None

    # Create workflow components and keep agent references
    # Pass project_client and credential to create separate client instances per agent
    workflow, agent_map = await _create_workflow(chat_client.project_client, chat_client.credential)

    # Process workflow events
    events = workflow.run_stream(query)
    workflow_output = await _process_workflow_events(events, conversation_ids, response_ids)

    return {
        "conversation_ids": dict(conversation_ids),
        "response_ids": dict(response_ids),
        "output": workflow_output,
        "query": query,
    }


async def _create_workflow(project_client, credential):
    """Create the multi-agent travel planning workflow with specialized agents.

    IMPORTANT: Each agent needs its own client instance because the V2 client stores
    agent_name and agent_version as instance variables, causing all agents to share
    the same agent identity if they share a client.
    """

    # Create separate client for Final Coordinator
    final_coordinator_client = AzureAIClient(
        project_client=project_client, credential=credential, agent_name="final-coordinator"
    )
    final_coordinator = ResearchLead(chat_client=final_coordinator_client, id="final-coordinator")

    # Agent 1: Travel Request Handler (initial coordinator)
    # Create separate client with unique agent_name
    travel_request_handler_client = AzureAIClient(
        project_client=project_client, credential=credential, agent_name="travel-request-handler"
    )
    travel_request_handler = travel_request_handler_client.as_agent(
        id="travel-request-handler",
        instructions=(
            "You receive user travel queries and relay them to specialized agents. Extract key information: destination, dates, budget, and preferences. Pass this information forward clearly to the next agents."
        ),
        name="travel-request-handler",
        store=True,
    )

    # Agent 2: Hotel Search Executor
    hotel_search_client = AzureAIClient(
        project_client=project_client, credential=credential, agent_name="hotel-search-agent"
    )
    hotel_search_agent = hotel_search_client.as_agent(
        id="hotel-search-agent",
        instructions=(
            "You are a hotel search specialist. Your task is ONLY to search for and provide hotel information. Use search_hotels to find options, get_hotel_details for specifics, and check_availability to verify rooms. Output format: List hotel names, prices per night, total cost for the stay, locations, ratings, amenities, and addresses. IMPORTANT: Only provide hotel information without additional commentary."
        ),
        name="hotel-search-agent",
        tools=[search_hotels, get_hotel_details, check_hotel_availability],
        store=True,
    )

    # Agent 3: Flight Search Executor
    flight_search_client = AzureAIClient(
        project_client=project_client, credential=credential, agent_name="flight-search-agent"
    )
    flight_search_agent = flight_search_client.as_agent(
        id="flight-search-agent",
        instructions=(
            "You are a flight search specialist. Your task is ONLY to search for and provide flight information. Use search_flights to find options, get_flight_details for specifics, and check_availability for seats. Output format: List flight numbers, airlines, departure/arrival times, prices, durations, and cabin class. IMPORTANT: Only provide flight information without additional commentary."
        ),
        name="flight-search-agent",
        tools=[search_flights, get_flight_details, check_flight_availability],
        store=True,
    )

    # Agent 4: Activity Search Executor
    activity_search_client = AzureAIClient(
        project_client=project_client, credential=credential, agent_name="activity-search-agent"
    )
    activity_search_agent = activity_search_client.as_agent(
        id="activity-search-agent",
        instructions=(
            "You are an activities specialist. Your task is ONLY to search for and provide activity information. Use search_activities to find options for activities. Output format: List activity names, descriptions, prices, durations, ratings, and categories. IMPORTANT: Only provide activity information without additional commentary."
        ),
        name="activity-search-agent",
        tools=[search_activities],
        store=True,
    )

    # Agent 5: Booking Confirmation Executor
    booking_confirmation_client = AzureAIClient(
        project_client=project_client, credential=credential, agent_name="booking-confirmation-agent"
    )
    booking_confirmation_agent = booking_confirmation_client.as_agent(
        id="booking-confirmation-agent",
        instructions=(
            "You confirm bookings. Use check_hotel_availability and check_flight_availability to verify slots, then confirm_booking to finalize. Provide ONLY: confirmation numbers, booking references, and confirmation status."
        ),
        name="booking-confirmation-agent",
        tools=[confirm_booking, check_hotel_availability, check_flight_availability],
        store=True,
    )

    # Agent 6: Booking Payment Executor
    booking_payment_client = AzureAIClient(
        project_client=project_client, credential=credential, agent_name="booking-payment-agent"
    )
    booking_payment_agent = booking_payment_client.as_agent(
        id="booking-payment-agent",
        instructions=(
            "You process payments. Use validate_payment_method to verify payment, then process_payment to complete transactions. Provide ONLY: payment confirmation status, transaction IDs, and payment amounts."
        ),
        name="booking-payment-agent",
        tools=[process_payment, validate_payment_method],
        store=True,
    )

    # Agent 7: Booking Information Aggregation Executor
    booking_info_client = AzureAIClient(
        project_client=project_client, credential=credential, agent_name="booking-info-aggregation-agent"
    )
    booking_info_aggregation_agent = booking_info_client.as_agent(
        id="booking-info-aggregation-agent",
        instructions=(
            "You aggregate hotel and flight search results. Receive options from search agents and organize them. Provide: top 2-3 hotel options with prices and top 2-3 flight options with prices in a structured format."
        ),
        name="booking-info-aggregation-agent",
        store=True,
    )

    # Build workflow with logical booking flow:
    # 1. start_executor → travel_request_handler
    # 2. travel_request_handler → hotel_search, flight_search, activity_search (fan-out)
    # 3. hotel_search → booking_info_aggregation
    # 4. flight_search → booking_info_aggregation
    # 5. booking_info_aggregation → booking_confirmation
    # 6. booking_confirmation → booking_payment
    # 7. booking_info_aggregation, booking_payment, activity_search → final_coordinator (final aggregation, fan-in)

    workflow = (
        WorkflowBuilder(name="Travel Planning Workflow")
        .set_start_executor(start_executor)
        .add_edge(start_executor, travel_request_handler)
        .add_fan_out_edges(travel_request_handler, [hotel_search_agent, flight_search_agent, activity_search_agent])
        .add_edge(hotel_search_agent, booking_info_aggregation_agent)
        .add_edge(flight_search_agent, booking_info_aggregation_agent)
        .add_edge(booking_info_aggregation_agent, booking_confirmation_agent)
        .add_edge(booking_confirmation_agent, booking_payment_agent)
        .add_fan_in_edges(
            [booking_info_aggregation_agent, booking_payment_agent, activity_search_agent], final_coordinator
        )
        .build()
    )

    # Return workflow and agent map for thread ID extraction
    agent_map = {
        "travel_request_handler": travel_request_handler,
        "hotel-search-agent": hotel_search_agent,
        "flight-search-agent": flight_search_agent,
        "activity-search-agent": activity_search_agent,
        "booking-confirmation-agent": booking_confirmation_agent,
        "booking-payment-agent": booking_payment_agent,
        "booking-info-aggregation-agent": booking_info_aggregation_agent,
        "final-coordinator": final_coordinator.agent,
    }

    return workflow, agent_map


async def _process_workflow_events(events, conversation_ids, response_ids):
    """Process workflow events and track interactions."""
    workflow_output = None

    async for event in events:
        if isinstance(event, WorkflowOutputEvent):
            workflow_output = event.data
            # Handle Unicode characters that may not be displayable in Windows console
            try:
                print(f"\nWorkflow Output: {event.data}\n")
            except UnicodeEncodeError:
                output_str = str(event.data).encode("ascii", "replace").decode("ascii")
                print(f"\nWorkflow Output: {output_str}\n")

        elif isinstance(event, AgentRunUpdateEvent):
            _track_agent_ids(event, event.executor_id, response_ids, conversation_ids)

    return workflow_output


def _track_agent_ids(event, agent, response_ids, conversation_ids):
    """Track agent response and conversation IDs - supporting multiple responses per agent."""
    if isinstance(event.data, AgentResponseUpdate):
        # Check for conversation_id and response_id from raw_representation
        # V2 API stores conversation_id directly on raw_representation (ChatResponseUpdate)
        if hasattr(event.data, "raw_representation") and event.data.raw_representation:
            raw = event.data.raw_representation

            # Try conversation_id directly on raw representation
            if hasattr(raw, "conversation_id") and raw.conversation_id:
                # Only add if not already in the list
                if raw.conversation_id not in conversation_ids[agent]:
                    conversation_ids[agent].append(raw.conversation_id)

            # Extract response_id from the OpenAI event (available from first event)
            if hasattr(raw, "raw_representation") and raw.raw_representation:
                openai_event = raw.raw_representation

                # Check if event has response object with id
                if hasattr(openai_event, "response") and hasattr(openai_event.response, "id"):
                    # Only add if not already in the list
                    if openai_event.response.id not in response_ids[agent]:
                        response_ids[agent].append(openai_event.response.id)


async def create_and_run_workflow():
    """Run the workflow evaluation and display results.

    Returns:
        Dictionary containing agents data with conversation IDs, response IDs, and query information
    """
    example_queries = [
        "Plan a 3-day trip to Paris from December 15-18, 2025. Budget is $2000. Need hotel near Eiffel Tower, round-trip flights from New York JFK, and recommend 2-3 activities per day.",
        "Find a budget hotel in Tokyo for January 5-10, 2026 under $150/night near Shibuya station, book activities including a sushi making class",
        "Search for round-trip flights from Los Angeles to London departing March 20, 2026, returning March 27, 2026. Economy class, 2 passengers. Recommend tourist attractions and museums.",
    ]

    query = example_queries[0]
    print(f"Query: {query}\n")

    result = await run_workflow_with_response_tracking(query)

    # Create output data structure
    output_data = {"agents": {}, "query": result["query"], "output": result.get("output", "")}

    # Create agent-specific mappings - now with lists of IDs
    all_agents = set(result["conversation_ids"].keys()) | set(result["response_ids"].keys())
    for agent_name in all_agents:
        output_data["agents"][agent_name] = {
            "conversation_ids": result["conversation_ids"].get(agent_name, []),
            "response_ids": result["response_ids"].get(agent_name, []),
            "response_count": len(result["response_ids"].get(agent_name, [])),
        }

    print(f"\nTotal agents tracked: {len(output_data['agents'])}")

    # Print summary of multiple responses
    print("\n=== Multi-Response Summary ===")
    for agent_name, agent_data in output_data["agents"].items():
        response_count = agent_data["response_count"]
        print(f"{agent_name}: {response_count} response(s)")

    return output_data


if __name__ == "__main__":
    asyncio.run(create_and_run_workflow())
