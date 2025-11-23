import uvicorn

from dotenv import load_dotenv
load_dotenv()

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

from agent_framework.a2a import A2aExecutor
from agent_framework.openai import OpenAIResponsesClient

if __name__ == '__main__':
    # --8<-- [start:AgentSkill]
    skill = AgentSkill(
        id='Food_Agent',
        name='Food Agent',
        description="A simple agent that provides food-related information.",
        tags=['food', 'nutrition', 'recipes'],
        examples=[],
    )
    # --8<-- [end:AgentSkill]

    # --8<-- [start:AgentCard]
    # This will be the public-facing agent card
    public_agent_card = AgentCard(
        name='Food Agent',
        description='A simple agent that provides food-related information.',
        url='http://localhost:9999/',
        version='1.0.0',
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )
    # --8<-- [end:AgentCard]

    agent = OpenAIResponsesClient().create_agent(
        name="Food Agent",
        instructions="A simple agent that provides food-related information.",
    )

    request_handler = DefaultRequestHandler(
        agent_executor= A2aExecutor(agent),
        task_store= InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=public_agent_card,
        http_handler=request_handler,
    )

    server = server.build()
    # print(schemas.get_schema(server.routes))

    uvicorn.run(server, host='0.0.0.0', port=9999)