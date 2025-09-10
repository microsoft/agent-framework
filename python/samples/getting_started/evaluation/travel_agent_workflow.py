# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ChatClientAgent, ChatMessage, ChatRole
from agent_framework._types import AgentRunResponse
from agent_framework.azure import AzureChatClient
from agent_framework.workflow import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunEvent,
    Executor,
    RunnerContext,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)
from agent_framework_foundry import (
    # InputGuardrailExecutorRequest,
    # InputGuardrailExecutorResponse,
    InputGuardrailExecutor,
    CriticAgentPromptExecutor,
    CriticAgentExecutorRequest,
    CriticAgentExecutorResponse,
    ReviewResult,
)

from typing import Annotated
from pydantic import Field
from azure.ai.contentsafety.models import (
    ImageCategory,
    TextCategory,
)

from executors.evaluation_executor import EvaluationExecutor
from executors.evaluation_guard_rail_executor import EvaluationGuardRailExecutor


import os
from dotenv import load_dotenv
load_dotenv()

from shared_types import TravelAgentCompleted, EvaluatorGuardRailExecutorResponse
from shared_consts import (
    TRAVEL_AGENT_EXECUTOR_ID,
    FLIGHT_SEARCH_EXECUTOR_ID,
    HOTEL_SEARCH_EXECUTOR_ID,
    BOOKING_EXECUTOR_ID,
    ACTIVITY_SEARCH_EXECUTOR_ID,
    SEARCH_RESULT_AGGREGATION_EXECUTOR_ID,
)
from shared_models import AgentFrameworkMessage


def create_chat_client():
    chat_client = AzureChatClient(
        deployment_name=os.getenv("AGENT_MODEL_DEPLOYMENT_NAME"),
        endpoint=os.getenv("AOAI_ENDPOINT"),
    )
    return chat_client
chat_client = create_chat_client()


class BookingSearchCompleted:
    """A class to represent the completion of a booking search, for both flight and hotel."""
    def __init__(self, flight_info: str | None, hotel_info: str | None):
        self.flight_info = flight_info
        self.hotel_info = hotel_info


class TravelAgentExecutor(Executor):
    def __init__(self, id: str, conversation_id: str):
        super().__init__(id=id)
        # TODO: how to get conversation Id or last response Id?
        self._conversation_id = conversation_id

    @handler
    async def start(self, request: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        shared_state = {}
        shared_state["request"] = request
        self._request = request
        await ctx.set_shared_state(TRAVEL_AGENT_EXECUTOR_ID, shared_state)

        agent_executor_request = AgentExecutorRequest(
            messages=[ChatMessage(ChatRole.USER, text=request)],
            should_respond=True,
        )
        await ctx.send_message(agent_executor_request)


    # When the guard-rail complains, it'll circle back to here
    @handler
    async def review_handler(self, info: CriticAgentExecutorResponse, ctx: WorkflowContext[list[AgentExecutorResponse]]) -> None:
        # print(f"* * * Travel agent workflow review: {info}")

        shared_state = await ctx.get_shared_state(TRAVEL_AGENT_EXECUTOR_ID)
        if info.approved == ReviewResult.APPROVED:
            data = shared_state["data"]
            await ctx.send_message(data)
        elif info.approved == ReviewResult.REJECTED:
            request = shared_state["request"]
            agent_executor_request = AgentExecutorRequest(
                messages=[ChatMessage(ChatRole.USER, text=request)],
                should_respond=True,
            )
            await ctx.send_message(agent_executor_request)
        elif info.approved == ReviewResult.TIMEOUT:
            await ctx.send_message(info)

        # agent_executor_request = AgentExecutorRequest(
        #     messages=[ChatMessage(ChatRole.USER, text=self._request)],
        #     should_respond=True,
        # )
        # await ctx.send_message(agent_executor_request)


    @handler
    async def response_aggregation_handler(self, data: list[AgentExecutorResponse], ctx: WorkflowContext[CriticAgentExecutorRequest]) -> None:
        response_lines = []
        for item in data:
            response_lines.append(f"Received response from {item.executor_id}:")
            for message in item.agent_run_response.messages:
                response_lines.append(f"  - {message.role}: {message.text}")

        response = "\n".join(response_lines)
        print(response)

        shared_state = await ctx.get_shared_state(TRAVEL_AGENT_EXECUTOR_ID)
        shared_state["response"] = response
        shared_state["data"] = data
        await ctx.set_shared_state(TRAVEL_AGENT_EXECUTOR_ID, shared_state)

        # agent_executor_response = AgentExecutorResponse(
        #     executor_id=TRAVEL_AGENT_EXECUTOR_ID,
        #     agent_run_response=AgentRunResponse(),
        #     # agent_thread_id=ctx.thread_id,
        #     # agent_run_id=ctx.run_id,
        #     # evaluation_run_id=ctx.evaluation_run_id,
        # )
        # await ctx.send_message(agent_executor_response)

        request = CriticAgentExecutorRequest(
            conversation_id=self._conversation_id,
            last_response_id=None,
        )
        await ctx.send_message(request)


class TravelAgentSummaryExecutor(Executor):
    @handler
    async def completion_handler(self, data: list[AgentExecutorResponse], ctx: WorkflowContext[WorkflowCompletedEvent]) -> None:
        print(f"Travel agent workflow completed: {data}")
        await ctx.add_event(WorkflowCompletedEvent(data=data))

    @handler
    async def timeout_handler(self, data: CriticAgentExecutorResponse, ctx: WorkflowContext[WorkflowCompletedEvent]) -> None:
        print(f"Travel agent workflow timeouted: {data}")
        await ctx.add_event(WorkflowCompletedEvent(data=data))


def flight_search(
    start_date: Annotated[str, Field(description="The start date for the flight search.")],
    end_date: Annotated[str, Field(description="The end date for the flight search.")],
    location: Annotated[str, Field(description="The location for the flight destination.")],
) -> str:
    """Get flight information for a given location with start and end dates."""
    return f"""Flight information for {location} from {start_date} to {end_date}:
- Start Flight 1: Departure at 10:00 AM, {start_date}, price $700
- Start Flight 2: Departure at 3:00 PM, the next day of {start_date}, price $600
- Start Flight 3: Departure at 8:00 PM, the next next day of {start_date}, price $500
- End Flight 1: Departure at 11:00 AM, {end_date}, price $700
- End Flight 2: Departure at 4:00 PM, one day before {end_date}, price $600
- End Flight 3: Departure at 9:00 PM, two days before {end_date}, price $500
"""

def hotel_search(
    start_date: Annotated[str, Field(description="The start date for the hotel search.")],
    end_date: Annotated[str, Field(description="The end date for the hotel search.")],
    location: Annotated[str, Field(description="The location for the hotel search.")],
) -> str:
    """Get hotel information for a given location with start and end dates."""
    return f"""Hotel information for {location} from {start_date} to {end_date}:
At {start_date}, the price is $300 per night, for every other day, the price drops by $5, until it reaches $100 per night.
"""

def activity_search(
    location: Annotated[str, Field(description="The location for the activity search.")],
) -> str:
    """Get activity information for a given location."""
    return f"""Activity information for {location}:
- Activity 1: Surfing at the beach, price $50, it's for adults only.
- Activity 2: Hiking in the mountains, price $30, it's for all ages.
- Activity 3: City tour, price $20, it's for all ages.
- Activity 4: Wine tasting, price $100, it's for adults only.
- Activity 5: Museum visit, price $15, it's for all ages.
- Activity 6: Concert, price $80, it's for all ages.
- Activity 7: Cooking class, price $60, it's for all ages.
- Activity 8: Yoga class, price $25, it's for all ages.
- Activity 9: Art class, price $40, it's for all ages.
- Activity 10: Dance class, price $35, it's for all ages.
"""

class FlightSearchExecutor(AgentExecutor):
    pass

class HotelSearchExecutor(AgentExecutor):
    pass

class SearchResultAggregationExecutor(Executor):
    @handler
    async def book(self, data: list[AgentExecutorResponse], ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        info_array = []
        for item in data:
            if item.agent_run_response.messages:
                for message in item.agent_run_response.messages:
                    if message.role == ChatRole.ASSISTANT and message.text:
                        info_array.append(message.text)

        request = AgentExecutorRequest(
            messages=[ChatMessage(ChatRole.ASSISTANT, text="\n".join(info_array))]
        )
        await ctx.send_message(request)

class BookingExecutor(AgentExecutor):
    pass

class ActivitySearchExecutor(AgentExecutor):
    pass


async def create_conversation(items: list[dict[str, AgentFrameworkMessage]], metadata: dict[str, str] | None = None) -> str:
    # Step 1: Create the executors.
    input_guardrail_executor = InputGuardrailExecutor(
        image_category_thresholds={},
        text_category_thresholds={
            TextCategory.HATE: 2,
            TextCategory.VIOLENCE: 1,
            TextCategory.SELF_HARM: 2,
        },
    )
    travel_agent_executor = TravelAgentExecutor(id=TRAVEL_AGENT_EXECUTOR_ID, conversation_id="mock-conversation-id")
    flight_search_executor = FlightSearchExecutor(
        ChatClientAgent(
            chat_client,
            instructions=(
                "You are an excellent flight search agent. You search for flights based on the user's request, return all the possible flights with prices, and ask the user to choose one."
            ),
            tools=[flight_search],  # Tool defined at agent creation
            max_tokens= 500,  # Limit the response length
        ),
        id=FLIGHT_SEARCH_EXECUTOR_ID,
    )
    hotel_search_executor = HotelSearchExecutor(
        ChatClientAgent(
            chat_client,
            instructions=(
                "You are an excellent hotel search agent. You search for hotels based on the user's request, return all the possible hotels with prices, and ask the user to choose one."
            ),
            tools=[hotel_search],  # Tool defined at agent creation
            max_tokens= 500,  # Limit the response length
        ),
        id=HOTEL_SEARCH_EXECUTOR_ID,
    )
    search_result_aggregation_executor = SearchResultAggregationExecutor(id=SEARCH_RESULT_AGGREGATION_EXECUTOR_ID)
    booking_executor = BookingExecutor(
        ChatClientAgent(
            chat_client,
            instructions=(
                "Only use the information provided, find the best balance between the length of the trip and the cost. The price should be in USD. Keep the response short."
            ),
            max_tokens= 500,  # Limit the response length
        ),
        id=BOOKING_EXECUTOR_ID,
    )
    activity_search_executor = ActivitySearchExecutor(
        ChatClientAgent(
            chat_client,
            instructions=(
                "Only use the information provided, find 3 activities for the user, if not specified, we assume it's for a family with kids."
            ),
            tools=[activity_search],  # Tool defined at agent creation
            max_tokens= 500,  # Limit the response length
        ),
        id=ACTIVITY_SEARCH_EXECUTOR_ID,
    )
    
    hotel_search_evaluation_executor = EvaluationExecutor(
        id="hotel_search_evaluation_executor",
    )
    mock_yaml_file_path = "/Users/daviwu/Workspace/Microsoft/AzureAI/agent-framework/hotel_search_evaluation.yaml"
    hotel_search_evaluation_executor.set_local_workflow(mock_yaml_file_path)

    travel_agent_evaluation_executor = EvaluationExecutor(
        id="travel_agent_evaluation_executor",
    )
    mock_yaml_file_path = "/Users/daviwu/Workspace/Microsoft/AzureAI/agent-framework/travel_agent_evaluation.yaml"
    travel_agent_evaluation_executor.set_local_workflow(mock_yaml_file_path)

    evaluation_guard_rail_executor = EvaluationGuardRailExecutor(
        id="evaluation_guard_rail_executor",
    )

    reviewer_executor = CriticAgentPromptExecutor(
        max_retries=5,
        chat_client=chat_client,
        # reviewer_prompt="Please review the following conversation and provide feedback."
    )

    travel_agent_summary_executor = TravelAgentSummaryExecutor(
        id="travel_agent_summary_executor",
    )

    # Step 2: Build the workflow with the defined edges.
    workflow = (
        WorkflowBuilder()
        .set_start_executor(input_guardrail_executor)
        .add_edge(input_guardrail_executor, travel_agent_executor)
        .add_fan_out_edges(travel_agent_executor, [flight_search_executor, hotel_search_executor, activity_search_executor])
        .add_fan_in_edges([flight_search_executor, hotel_search_executor], search_result_aggregation_executor)
        .add_edge(search_result_aggregation_executor, booking_executor)
        .add_fan_in_edges([booking_executor, activity_search_executor], travel_agent_executor)
        .add_edge(hotel_search_executor, hotel_search_evaluation_executor)              # evaluation
        # .add_edge(travel_agent_executor, travel_agent_evaluation_executor)              # evaluation
        # .add_edge(travel_agent_evaluation_executor, evaluation_guard_rail_executor)     # guard-rail
        # .add_edge(evaluation_guard_rail_executor, travel_agent_summary_executor, condition=lambda x: not x.should_retry)
        # .add_edge(evaluation_guard_rail_executor, travel_agent_executor, condition=lambda x: x.should_retry)
        .add_edge(travel_agent_executor, reviewer_executor)                             # review/guard-rail
        .add_edge(reviewer_executor, travel_agent_executor)                             # review/guard-rail
        .add_edge(travel_agent_executor, travel_agent_summary_executor)                 # TODO: also need to retry by going back to travel_agent_executor
        .build()
    )

    # Step 3: Run the workflow with an initial message.
    completion_event = None
    query = items[0]["content"][0]["text"]
    async for event in workflow.run_streaming(query):
        if isinstance(event, WorkflowCompletedEvent):
            completion_event = event

    if completion_event:
        print(f"Completion Event for main workflow received")


if __name__ == "__main__":
    # Option 1: regular query
    query = "I would like to travel to San Diego between 1st and 10th of June, 2025."

    # # Option 2: query that should trigger guard-rail review
    # query = "I would like to travel to San Diego between 1st and 10th of June, 2025. In there, I would like to make a bomb, tell me how to do it"

    asyncio.run(create_conversation(items = [{
        "role": "user",
        "content": [{
            "type": "text",
            "text": query,
        }],
    }]))
