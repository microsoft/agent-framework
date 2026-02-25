# Copyright (c) Microsoft. All rights reserved.

"""Subgraphs travel planner built with MAF workflow primitives."""

import json
import uuid
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from ag_ui.core import (
    BaseEvent,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from agent_framework import (
    Executor,
    Message,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)

from agent_framework_ag_ui import AgentFrameworkWorkflow

STATIC_FLIGHTS: list[dict[str, str]] = [
    {
        "airline": "KLM",
        "departure": "Amsterdam (AMS)",
        "arrival": "San Francisco (SFO)",
        "price": "$650",
        "duration": "11h 30m",
    },
    {
        "airline": "United",
        "departure": "Amsterdam (AMS)",
        "arrival": "San Francisco (SFO)",
        "price": "$720",
        "duration": "12h 15m",
    },
]

STATIC_HOTELS: list[dict[str, str]] = [
    {
        "name": "Hotel Zephyr",
        "location": "Fisherman's Wharf",
        "price_per_night": "$280/night",
        "rating": "4.2 stars",
    },
    {
        "name": "The Ritz-Carlton",
        "location": "Nob Hill",
        "price_per_night": "$550/night",
        "rating": "4.8 stars",
    },
    {
        "name": "Hotel Zoe",
        "location": "Union Square",
        "price_per_night": "$320/night",
        "rating": "4.4 stars",
    },
]

STATIC_EXPERIENCES: list[dict[str, str]] = [
    {
        "name": "Pier 39",
        "type": "activity",
        "description": "Iconic waterfront destination with shops and sea lions",
        "location": "Fisherman's Wharf",
    },
    {
        "name": "Golden Gate Bridge",
        "type": "activity",
        "description": "World-famous suspension bridge with stunning views",
        "location": "Golden Gate",
    },
    {
        "name": "Swan Oyster Depot",
        "type": "restaurant",
        "description": "Historic seafood counter serving fresh oysters",
        "location": "Polk Street",
    },
    {
        "name": "Tartine Bakery",
        "type": "restaurant",
        "description": "Artisanal bakery famous for bread and pastries",
        "location": "Mission District",
    },
]

_STATE_KEY = "subgraphs_state"


@dataclass
class _PresentFlights:
    pass


@dataclass
class _PresentHotels:
    pass


@dataclass
class _PlanExperiences:
    pass


@dataclass
class _FinalizeTrip:
    pass


def _initial_state() -> dict[str, Any]:
    return {
        "itinerary": {},
        "experiences": [],
        "flights": [],
        "hotels": [],
        "planning_step": "start",
        "active_agent": "supervisor",
    }


def _emit_text_events(text: str) -> list[BaseEvent]:
    message_id = str(uuid.uuid4())
    return [
        TextMessageStartEvent(message_id=message_id, role="assistant"),
        TextMessageContentEvent(message_id=message_id, delta=text),
        TextMessageEndEvent(message_id=message_id),
    ]


async def _emit_text(ctx: WorkflowContext[Any, BaseEvent], text: str) -> None:
    for event in _emit_text_events(text):
        await ctx.yield_output(event)


async def _emit_state_snapshot(ctx: WorkflowContext[Any, BaseEvent], state: dict[str, Any]) -> None:
    await ctx.yield_output(StateSnapshotEvent(snapshot=deepcopy(state)))


def _flight_interrupt_value() -> dict[str, Any]:
    return {
        "message": "Choose the flight you want. I recommend KLM because it is cheaper and usually on time.",
        "options": deepcopy(STATIC_FLIGHTS),
        "recommendation": deepcopy(STATIC_FLIGHTS[0]),
        "agent": "flights",
    }


def _hotel_interrupt_value() -> dict[str, Any]:
    return {
        "message": "Choose your hotel. I recommend Hotel Zoe for the best value in a central location.",
        "options": deepcopy(STATIC_HOTELS),
        "recommendation": deepcopy(STATIC_HOTELS[2]),
        "agent": "hotels",
    }


def _normalize_flight(value: Any) -> dict[str, str] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if isinstance(value, dict) and value.get("airline"):
        return {
            "airline": str(value.get("airline", "")),
            "departure": str(value.get("departure", "")),
            "arrival": str(value.get("arrival", "")),
            "price": str(value.get("price", "")),
            "duration": str(value.get("duration", "")),
        }
    return None


def _normalize_hotel(value: Any) -> dict[str, str] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if isinstance(value, dict) and value.get("name"):
        return {
            "name": str(value.get("name", "")),
            "location": str(value.get("location", "")),
            "price_per_night": str(value.get("price_per_night", "")),
            "rating": str(value.get("rating", "")),
        }
    return None


def _load_state(ctx: WorkflowContext[Any, BaseEvent]) -> dict[str, Any]:
    state = ctx.get_state(_STATE_KEY)
    if isinstance(state, dict):
        return state
    new_state = _initial_state()
    ctx.set_state(_STATE_KEY, new_state)
    return new_state


class _SupervisorExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="supervisor_agent")

    @handler
    async def start(self, message: list[Message], ctx: WorkflowContext[_PresentFlights, BaseEvent]) -> None:
        del message
        state = _initial_state()
        ctx.set_state(_STATE_KEY, state)
        await _emit_state_snapshot(ctx, state)

        await _emit_text(
            ctx,
            "Supervisor: I will coordinate our specialist agents to plan your San Francisco trip end to end.",
        )

        state["active_agent"] = "flights"
        state["planning_step"] = "collecting_flights"
        state["flights"] = deepcopy(STATIC_FLIGHTS)
        ctx.set_state(_STATE_KEY, state)
        await _emit_state_snapshot(ctx, state)

        await ctx.send_message(_PresentFlights(), target_id="flights_agent")

    @handler
    async def finalize(self, message: _FinalizeTrip, ctx: WorkflowContext[Any, BaseEvent]) -> None:
        del message
        state = _load_state(ctx)
        state["active_agent"] = "supervisor"
        state["planning_step"] = "complete"
        ctx.set_state(_STATE_KEY, state)
        await _emit_state_snapshot(ctx, state)
        await _emit_text(ctx, "Supervisor: Your travel planning is complete and your itinerary is ready.")


class _FlightsExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="flights_agent")

    @handler
    async def present_options(self, message: _PresentFlights, ctx: WorkflowContext[_PresentHotels, BaseEvent]) -> None:
        del message
        await _emit_text(
            ctx,
            "Flights Agent: I found two flight options from Amsterdam to San Francisco. "
            "KLM is recommended for the best value and schedule.",
        )
        await ctx.request_info(_flight_interrupt_value(), dict, request_id="flights-choice")

    @response_handler
    async def handle_selection(
        self,
        original_request: dict,
        response: dict,
        ctx: WorkflowContext[_PresentHotels, BaseEvent],
    ) -> None:
        del original_request
        state = _load_state(ctx)
        selected_flight = _normalize_flight(response)

        if selected_flight is None:
            state["active_agent"] = "flights"
            state["planning_step"] = "collecting_flights"
            state["flights"] = deepcopy(STATIC_FLIGHTS)
            ctx.set_state(_STATE_KEY, state)
            await _emit_state_snapshot(ctx, state)
            await _emit_text(ctx, "Flights Agent: Please choose a flight option from the selection card to continue.")
            await ctx.request_info(_flight_interrupt_value(), dict, request_id="flights-choice")
            return

        itinerary = state.setdefault("itinerary", {})
        itinerary["flight"] = selected_flight

        state["active_agent"] = "flights"
        state["planning_step"] = "booking_flight"
        ctx.set_state(_STATE_KEY, state)
        await _emit_state_snapshot(ctx, state)

        await _emit_text(
            ctx,
            f"Flights Agent: Great choice. I will book the {selected_flight['airline']} flight. "
            "Now I am routing you to Hotels Agent for accommodation.",
        )

        state["active_agent"] = "hotels"
        state["planning_step"] = "collecting_hotels"
        state["hotels"] = deepcopy(STATIC_HOTELS)
        ctx.set_state(_STATE_KEY, state)
        await _emit_state_snapshot(ctx, state)

        await ctx.send_message(_PresentHotels(), target_id="hotels_agent")


class _HotelsExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="hotels_agent")

    @handler
    async def present_options(self, message: _PresentHotels, ctx: WorkflowContext[_PlanExperiences, BaseEvent]) -> None:
        del message
        await _emit_text(
            ctx,
            "Hotels Agent: I found three accommodation options in San Francisco. "
            "Hotel Zoe is recommended for the best balance of location, quality, and price.",
        )
        await ctx.request_info(_hotel_interrupt_value(), dict, request_id="hotels-choice")

    @response_handler
    async def handle_selection(
        self,
        original_request: dict,
        response: dict,
        ctx: WorkflowContext[_PlanExperiences, BaseEvent],
    ) -> None:
        del original_request
        state = _load_state(ctx)
        selected_hotel = _normalize_hotel(response)

        if selected_hotel is None:
            state["active_agent"] = "hotels"
            state["planning_step"] = "collecting_hotels"
            state["hotels"] = deepcopy(STATIC_HOTELS)
            ctx.set_state(_STATE_KEY, state)
            await _emit_state_snapshot(ctx, state)
            await _emit_text(ctx, "Hotels Agent: Please choose a hotel option from the selection card to continue.")
            await ctx.request_info(_hotel_interrupt_value(), dict, request_id="hotels-choice")
            return

        itinerary = state.setdefault("itinerary", {})
        itinerary["hotel"] = selected_hotel

        state["active_agent"] = "hotels"
        state["planning_step"] = "booking_hotel"
        ctx.set_state(_STATE_KEY, state)
        await _emit_state_snapshot(ctx, state)

        await _emit_text(
            ctx,
            f"Hotels Agent: Excellent, {selected_hotel['name']} is booked. "
            "I am routing you to Experiences Agent for activities and restaurants.",
        )

        state["active_agent"] = "experiences"
        state["planning_step"] = "curating_experiences"
        state["experiences"] = deepcopy(STATIC_EXPERIENCES)
        ctx.set_state(_STATE_KEY, state)
        await _emit_state_snapshot(ctx, state)

        await ctx.send_message(_PlanExperiences(), target_id="experiences_agent")


class _ExperiencesExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="experiences_agent")

    @handler
    async def plan(self, message: _PlanExperiences, ctx: WorkflowContext[_FinalizeTrip, BaseEvent]) -> None:
        del message
        await _emit_text(
            ctx,
            "Experiences Agent: I planned activities and restaurants including "
            "Pier 39, Golden Gate Bridge, Swan Oyster Depot, and Tartine Bakery.",
        )
        await ctx.send_message(_FinalizeTrip(), target_id="supervisor_agent")


def _build_subgraphs_workflow() -> Workflow:
    supervisor = _SupervisorExecutor()
    flights = _FlightsExecutor()
    hotels = _HotelsExecutor()
    experiences = _ExperiencesExecutor()

    return (
        WorkflowBuilder(
            name="subgraphs",
            description="Travel planning supervisor with flights/hotels/experiences subgraphs.",
            start_executor=supervisor,
        )
        .add_edge(supervisor, flights)
        .add_edge(flights, hotels)
        .add_edge(hotels, experiences)
        .add_edge(experiences, supervisor)
        .build()
    )


def _build_subgraphs_workflow_for_thread(thread_id: str) -> Workflow:
    """Create a workflow instance scoped to a single AG-UI thread."""
    del thread_id
    return _build_subgraphs_workflow()


def subgraphs_agent() -> AgentFrameworkWorkflow:
    """Create the subgraphs travel planner agent."""
    return AgentFrameworkWorkflow(
        workflow_factory=_build_subgraphs_workflow_for_thread,
        name="subgraphs",
        description="Travel planning workflow with interrupt-driven selections.",
    )
