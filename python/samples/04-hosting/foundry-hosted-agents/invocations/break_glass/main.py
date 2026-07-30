# Copyright (c) Microsoft. All rights reserved.

import os
from collections.abc import AsyncGenerator

from agent_framework import Agent, AgentSession
from agent_framework.foundry import FoundryChatClient
from azure.ai.agentserver.core import get_request_context
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

# Load environment variables from .env file
load_dotenv()


# In-memory session store — keyed by session ID.
# WARNING: This is lost on restart. Use durable storage in production.
_sessions: dict[str, AgentSession] = {}

# Create the agent
client = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    credential=DefaultAzureCredential(),
)

agent = Agent(
    client=client,
    instructions="You are a friendly assistant. Keep your answers brief.",
    # History will be managed by the hosting infrastructure, thus there
    # is no need to store history by the service. Learn more at:
    # https://developers.openai.com/api/reference/resources/responses/methods/create
    default_options={"store": False},
)

app = InvocationAgentServerHost()


def get_session_partition_key() -> str:
    """Get the partition key for the current request.

    A partition key is made up of the session ID and user ID. If the request is not
    from a hosted environment, the partition key will be just the session ID. In the
    Foundry hosted environment, the partition key is used to maintain isolation between
    different sessions and users, such that one user cannot access another user's sessions.

    Returns:
        The partition key for the current request.
    """
    context = get_request_context()
    if context.session_id is None:
        raise RuntimeError(
            "The request context is missing session_id. Please ensure that the request is a valid request."
        )
    if context.user_id is not None:
        return f"{context.session_id}:{context.user_id}"
    return context.session_id


@app.invoke_handler
async def handle_invoke(request: Request):
    """Handle streaming multi-turn chat with Azure OpenAI via SSE."""
    data = await request.json()
    stream = data.get("stream", False)
    user_message = data.get("message", None)
    if user_message is None:
        error = "Missing 'message' in request"
        if stream:
            return StreamingResponse(content=error, status_code=400)
        return Response(content=error, status_code=400)

    session_id = get_session_partition_key()
    session = _sessions.setdefault(session_id, AgentSession(session_id=session_id))

    if stream:

        async def stream_response() -> AsyncGenerator[str]:
            async for update in agent.run(user_message, session=session, stream=True):
                yield update.text

        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    response = await agent.run([user_message], session=session, stream=stream)
    return Response(content=response.text)


if __name__ == "__main__":
    app.run()
