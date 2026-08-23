# Copyright (c) Microsoft. All rights reserved.

"""A2UI (agent-generated UI) example agents.

Four dojo demos mirroring the .NET / AWS Strands / LangGraph A2UI samples:

* ``a2ui_dynamic_schema_agent`` — happy path: a valid surface is generated from the
  frontend-supplied component catalog, with a backend composition guide.
* ``a2ui_advanced_agent`` — ZERO-CONFIG: no backend catalog or composition guide. The
  catalog schema and ``injectA2UITool`` arrive on ``forwardedProps`` from the frontend;
  the adapter auto-injects ``generate_a2ui`` and the render sub-agent composes against
  the forwarded catalog. Proves the easy-devex path (a plain agent + a client catalog).
* ``a2ui_recovery_agent`` — exercises the validate→retry recovery loop when the render
  sub-agent first emits an invalid surface; deterministic under aimock fixtures.
* ``a2ui_fixed_schema_agent`` — direct-tool (NO subagent/recovery): plain backend tools
  (``search_flights`` / ``search_hotels``) return a pre-authored ``a2ui_operations``
  envelope as a JSON STRING; the runtime A2UI middleware detects it in the tool result
  and paints. Only the DATA changes per call. Works even when the runtime forwards
  ``injectA2UITool`` because
  ``A2UIAgent`` passes non-``generate_a2ui`` tool calls (and their results) straight
  through to the inner function-invoker, so the fixed tool's envelope still paints.

The first three are PLAIN agents with NO a2ui wiring. The dojo's copilotkit route sends
``forwardedProps.injectA2UITool``; the adapter auto-injects ``generate_a2ui`` and infers
the render sub-agent from the agent's chat client. Pass :data:`A2UI_DEMO_CONFIG` as the
endpoint's ``a2ui_config`` so auto-injected surfaces reference the dojo catalog (the
zero-config ``a2ui_advanced`` demo passes no config).

Use a Chat-Completions client (``OpenAIChatCompletionClient``) for these agents: it
streams ``render_a2ui`` argument deltas (progressive paint) and replays the balancing
tool result cleanly, where the Responses-API client (``OpenAIChatClient``)
buffers/rejects.
"""

from typing import Any

from agent_framework import Agent, tool

# The dojo registers its dynamic component catalog (HotelCard, ProductCard,
# TeamMemberCard, StarRating, Row) under this id; auto-injected surfaces must
# reference it so the renderer can resolve their components.
DOJO_CATALOG_ID = "https://a2ui.org/demos/dojo/dynamic_catalog.json"

# Teaches the render sub-agent how to compose the dojo catalog's components.
# Mirrors the LangGraph / Strands dynamic-schema COMPOSITION_GUIDE so a real
# model (not just the aimock fixtures) can produce valid surfaces.
COMPOSITION_GUIDE = """
## Available Pre-made Components

You have card components plus a Row container. Use Row as the root with structural
children to repeat a card per item.

### Row
Layout container. Repeat a card template via structural children:
  {"id":"root","component":"Row","children":{"componentId":"card","path":"/items"}}

### HotelCard
Props: name, location, rating (number 0-5), pricePerNight, action

### ProductCard
Props: name, price, rating (number 0-5), description (optional), action

### TeamMemberCard
Props: name, role, department (optional), email (optional), action

## RULES
- Root is ALWAYS a Row with structural children: {"componentId":"<card-id>","path":"/items"}
- ALWAYS include the referenced card component in the components array.
- Inside templates use RELATIVE paths (no leading slash): {"path":"name"}.
- Always provide data in the "data" argument as {"items":[...]}.
- Pick the card type that best matches the request; generate 3-4 realistic items.
"""

#: Backend A2UI config for the dojo demos, passed as ``a2ui_config`` to
#: ``add_agent_framework_fastapi_endpoint``. Consumed by auto-injection.
A2UI_DEMO_CONFIG: dict[str, Any] = {
    "default_catalog_id": DOJO_CATALOG_ID,
    "guidelines": {"composition_guide": COMPOSITION_GUIDE},
}

_SYSTEM_PROMPT = (
    "You are a helpful assistant that creates rich visual UI on the fly. When the user "
    "asks for visual content (product comparisons, dashboards, team rosters, lists, "
    "cards, etc.), use the generate_a2ui tool to create a dynamic A2UI surface. "
    "IMPORTANT: after calling the tool, do NOT repeat the data in your text response — "
    "the tool renders UI automatically. Just confirm what was rendered."
)


def a2ui_dynamic_schema_agent(client: Any) -> Agent[Any]:
    """Plain agent for the A2UI dynamic-schema demo (auto-injected generate_a2ui)."""
    return Agent[Any](name="a2ui_dynamic_schema", instructions=_SYSTEM_PROMPT, client=client)


def a2ui_advanced_agent(client: Any) -> Agent[Any]:
    """Plain agent for the ZERO-CONFIG A2UI demo.

    Identical to the dynamic-schema agent but its endpoint passes NO ``a2ui_config``:
    the catalog schema arrives on ``forwardedProps`` and the render sub-agent composes
    against it with only the toolkit's built-in generation/design guidelines. This is
    the "a plain agent plus a client catalog is enough" path.
    """
    return Agent[Any](name="a2ui_advanced", instructions=_SYSTEM_PROMPT, client=client)


def a2ui_recovery_agent(client: Any) -> Agent[Any]:
    """Plain agent for the A2UI recovery demo (auto-injected generate_a2ui)."""
    return Agent[Any](name="a2ui_recovery", instructions=_SYSTEM_PROMPT, client=client)


# --------------------------------------------------------------------------- #
# Fixed-schema (direct-tool) demo
# --------------------------------------------------------------------------- #

# Custom fixed catalog id the dojo's a2ui_fixed_schema page registers (StarRating +
# HotelCard). The component TREE is authored ahead of time here; only the DATA
# (the hotel list) changes per call. Mirrors the LangGraph fixed-schema demo.
FIXED_CATALOG_ID = "https://a2ui.org/demos/dojo/fixed_catalog.json"
FLIGHT_SURFACE_ID = "flight-search-results"
HOTEL_SURFACE_ID = "hotel-search-results"

# Pre-authored A2UI v0.9 component array: a Row repeating a FlightCard per /flights item.
FLIGHT_SCHEMA: list[dict[str, Any]] = [
    {
        "id": "root",
        "component": "Row",
        "children": {"componentId": "flight-card", "path": "/flights"},
        "gap": 16,
    },
    {
        "id": "flight-card",
        "component": "FlightCard",
        "airline": {"path": "airline"},
        "airlineLogo": {"path": "airlineLogo"},
        "flightNumber": {"path": "flightNumber"},
        "origin": {"path": "origin"},
        "destination": {"path": "destination"},
        "date": {"path": "date"},
        "departureTime": {"path": "departureTime"},
        "arrivalTime": {"path": "arrivalTime"},
        "duration": {"path": "duration"},
        "status": {"path": "status"},
        "price": {"path": "price"},
        "action": {
            "event": {
                "name": "book_flight",
                "context": {
                    "flightNumber": {"path": "flightNumber"},
                    "origin": {"path": "origin"},
                    "destination": {"path": "destination"},
                    "price": {"path": "price"},
                },
            }
        },
    },
]

# Pre-authored A2UI v0.9 component array: a Row repeating a HotelCard per /hotels item.
HOTEL_SCHEMA: list[dict[str, Any]] = [
    {
        "id": "root",
        "component": "Row",
        "children": {"componentId": "hotel-card", "path": "/hotels"},
        "gap": 16,
    },
    {
        "id": "hotel-card",
        "component": "HotelCard",
        "name": {"path": "name"},
        "location": {"path": "location"},
        "rating": {"path": "rating"},
        "pricePerNight": {"path": "price"},
        "action": {
            "event": {
                "name": "book_hotel",
                "context": {"hotelName": {"path": "name"}, "price": {"path": "price"}},
            }
        },
    },
]

_FIXED_SYSTEM_PROMPT = (
    "You are a helpful travel assistant. When the user asks about flights, call the "
    "search_flights tool; when they ask about hotels, call the search_hotels tool. "
    "Provide 3-4 realistic results. "
    "IMPORTANT: after calling the tool, do NOT repeat the data in your text response — "
    "the tool renders rich UI automatically. Just say something brief like 'Here are "
    "your results.'"
)


@tool
def search_flights(flights: list[dict[str, Any]]) -> str:
    """Search for flights and display the results as rich cards.

    Each flight must have: id, airline, airlineLogo (a logo URL), flightNumber,
    origin, destination, date, departureTime, arrivalTime, duration, status, and
    price (e.g. "$289"). Generate 3-4 realistic flight results.

    Returns:
        The A2UI operations envelope (JSON string) the runtime middleware paints.
    """
    from ag_ui_a2ui_toolkit import (
        create_surface,
        update_components,
        update_data_model,
        wrap_as_operations_envelope,
    )

    return wrap_as_operations_envelope(
        [
            create_surface(FLIGHT_SURFACE_ID, FIXED_CATALOG_ID),
            update_components(FLIGHT_SURFACE_ID, FLIGHT_SCHEMA),
            update_data_model(FLIGHT_SURFACE_ID, {"flights": flights}),
        ]
    )


@tool
def search_hotels(hotels: list[dict[str, Any]]) -> str:
    """Search for hotels and display the results as rich cards with star ratings.

    Each hotel must have: id, name (e.g. "The Plaza"), location (e.g. "Midtown
    Manhattan, NYC"), rating (float 0-5, e.g. 4.5), and price (per night, e.g. "$350").
    Generate 3-4 realistic hotel results.

    Returns:
        The A2UI operations envelope (JSON string) the runtime middleware paints.
    """
    # Import the toolkit lazily so the examples package imports without the optional
    # ag-ui-a2ui-toolkit dependency unless the fixed-schema demo is actually used.
    from ag_ui_a2ui_toolkit import (
        create_surface,
        update_components,
        update_data_model,
        wrap_as_operations_envelope,
    )

    return wrap_as_operations_envelope(
        [
            create_surface(HOTEL_SURFACE_ID, FIXED_CATALOG_ID),
            update_components(HOTEL_SURFACE_ID, HOTEL_SCHEMA),
            update_data_model(HOTEL_SURFACE_ID, {"hotels": hotels}),
        ]
    )


def a2ui_fixed_schema_agent(client: Any) -> Agent[Any]:
    """Plain agent for the fixed-schema (direct-tool) A2UI demo.

    Wires its OWN ``search_flights`` / ``search_hotels`` backend tools whose results are
    complete ``a2ui_operations`` envelopes — no ``generate_a2ui``, no render sub-agent,
    no recovery loop. The pre-authored :data:`FLIGHT_SCHEMA` / :data:`HOTEL_SCHEMA` bind
    to the frontend's fixed catalog; only the data varies per call.
    """
    return Agent[Any](
        name="a2ui_fixed_schema",
        instructions=_FIXED_SYSTEM_PROMPT,
        client=client,
        tools=[search_flights, search_hotels],
    )
