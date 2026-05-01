# Copyright (c) Microsoft. All rights reserved.

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from agent_framework import Agent
from agent_framework.a2a import A2AExecutor
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    # --8<-- [start:AgentSkill]
    flight_skill = AgentSkill(
        id="Flight_Booking",
        name="Flight Booking",
        description="Search and book flights across Europe.",
        tags=["flights", "travel", "europe"],
        examples=[],
    )
    hotel_skill = AgentSkill(
        id="Hotel_Booking",
        name="Hotel Booking",
        description="Search and book hotels across Europe.",
        tags=["hotels", "travel", "accommodation"],
        examples=[],
    )
    # --8<-- [end:AgentSkill]

    # --8<-- [start:AgentCard]
    # This will be the public-facing agent card
    public_agent_card = AgentCard(
        name="Europe Travel Agent",
        description="A helpful Europe Travel Agent that can help users search and book flights and hotels across Europe.",
        url="http://localhost:9999/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[flight_skill, hotel_skill],
    )
    # --8<-- [end:AgentCard]

    agent = Agent(
        client=OpenAIChatClient(),
        name="Europe Travel Agent",
        instructions="You are a helpful Europe Travel Agent. You can help users search and book flights and hotels across Europe.",
    )

    request_handler = DefaultRequestHandler(
        agent_executor=A2AExecutor(agent),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=public_agent_card,
        http_handler=request_handler,
    )

    server = server.build()
    # print(schemas.get_schema(server.routes))

    uvicorn.run(server, host="0.0.0.0", port=9999)
