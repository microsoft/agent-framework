# Copyright (c) Microsoft. All rights reserved.

from agent_framework import AgentSession, BaseAgent, SupportsAgentRun
from azure.ai.agentserver.core import get_request_context
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
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
        self.invoke_handler(self._handle_invoke)

    def _partition_key(self) -> str:
        """Get the partition key for the current request.

        A partition key is made up of the session ID and user ID. If the request is not
        from a hosted environment, the partition key will be just the session ID. In the
        Foundry hosted environment, the partition key is used to maintain isolation between
        different sessions and users, such that one user cannot access another user's sessions.

        Returns:
            The partition key for the current request.

        Exceptions:
            RuntimeError: If the context doesn't contain the expected IDs.
        """
        context = get_request_context()

        # Fail fast if the service is on protocol v1.0.0
        if self.config.is_hosted and context.call_id is None:
            raise RuntimeError(
                "The hosted environment is running on protocol 1.0.0, but the agent requires protocol 2.0.0. "
                "Please upgrade your agent protocol to 2.0.0 in `agent.manifest.yaml` or `agent.yaml`, or "
                "downgrade the `agent-framework-foundry-hosting` package to `1.0.0a260625` or before to use 1.0.0."
            )

        if self.config.is_hosted:
            if not context.session_id or not context.user_id:
                raise RuntimeError(
                    "The hosted environment is missing session_id or user_id in the request context. "
                    "Please ensure that the request is coming from a valid Foundry platform service."
                )
            return f"{context.session_id}:{context.user_id}"

        if not context.session_id:
            raise RuntimeError(
                "The request context is missing session_id. Please ensure that the request is a valid request."
            )

        return context.session_id

    async def _handle_invoke(self, request: Request) -> Response:
        """Invoke the agent with the given request."""
        try:
            session_id = self._partition_key()
        except Exception as e:
            return Response(content=str(e), status_code=500)

        data = await request.json()

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

        response = await self._agent.run([user_message], session=session)
        return Response(content=response.text)
