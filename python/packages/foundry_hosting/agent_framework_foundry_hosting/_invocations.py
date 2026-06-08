# Copyright (c) Microsoft. All rights reserved.

from agent_framework import AgentSession, BaseAgent, SupportsAgentRun
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from typing_extensions import Any, AsyncGenerator


class InvocationsHostServer(InvocationAgentServerHost):
    """An invocations server host for an agent."""

    def __init__(
        self,
        agent: BaseAgent,
        *,
        openapi_spec: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an InvocationsHostServer.

        Args:
            agent: The agent to handle responses for.
            openapi_spec: The OpenAPI specification for the server.
            **kwargs: Additional keyword arguments.

        This host will expect the request to be a JSON body with a "message" field.
        The response from the host will be a JSON object with a "response" field containing
        the agent's response and a "session_id" field containing the session ID.
        """
        super().__init__(openapi_spec=openapi_spec, **kwargs)

        if not isinstance(agent, SupportsAgentRun):
            raise TypeError("Agent must support the SupportsAgentRun interface")

        self._agent = agent
        self._sessions: dict[str, AgentSession] = {}
        self.invoke_handler(self._handle_invoke)  # pyright: ignore[reportUnknownMemberType]

    async def _handle_invoke(self, request: Request) -> Response:
        """Invoke the agent with the given request."""
        data = await request.json()
        session_id: str = request.state.session_id

        stream = data.get("stream", False)
        user_message = data.get("message", None)
        if user_message is None:
            error = "Missing 'message' in request"
            if stream:
                return StreamingResponse(content=error, status_code=400)
            return Response(content=error, status_code=400)

        session = self._sessions.setdefault(session_id, AgentSession(session_id=session_id))

        if stream:

            async def stream_response() -> AsyncGenerator[str]:
                async for update in self._agent.run(user_message, session=session, stream=True):
                    if update.text:
                        yield update.text

            return StreamingResponse(
                stream_response(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )

        response = await self._agent.run([user_message], session=session, stream=stream)
        return JSONResponse({
            "response": response.text,
            "session_id": session_id,
        })
