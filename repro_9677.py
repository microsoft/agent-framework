import asyncio
from collections.abc import AsyncIterable
from agent_framework import (
    Agent,
    AgentSession,
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
    ToolApprovalMiddleware,
    tool,
)

executed = []

@tool
def lookup(query: str) -> str:
    executed.append(query)
    return f"result for {query}"

class ScriptedClient(FunctionInvocationLayer, ChatMiddlewareLayer, BaseChatClient):
    def __init__(self, turns, **kwargs):
        super().__init__(**kwargs)
        self.turns = list(turns)
        self.tool_choices = []

    def _next(self, options):
        self.tool_choices.append(options.get("tool_choice"))
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn

    def _inner_get_response(self, *, messages, stream, options, **kwargs):
        if stream:
            async def updates() -> AsyncIterable[ChatResponseUpdate]:
                yield ChatResponseUpdate(role="assistant", contents=[self._next(options)])
            return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

        async def get() -> ChatResponse:
            return ChatResponse(messages=[Message(role="assistant", contents=[self._next(options)])])
        return get()

async def main(stream: bool) -> None:
    executed.clear()
    client = ScriptedClient(
        [
            Content.from_function_call(call_id="c1", name="lookup", arguments='{"query": "first"}'),
            RuntimeError("transient provider error"),
            Content.from_function_call(call_id="c2", name="lookup", arguments='{"query": "retry"}'),
            Content.from_text("final answer"),
        ],
        function_invocation_configuration={"max_iterations": 2},
    )
    agent = Agent(client=client, tools=[lookup], middleware=[ToolApprovalMiddleware()])
    session = AgentSession()

    async def run(text: str):
        if stream:
            response_stream = agent.run(text, session=session, stream=True)
            async for _ in response_stream:
                pass
            return await response_stream.get_final_response()
        return await agent.run(text, session=session)

    print(f"stream={stream}")
    try:
        await run("look it up")
    except RuntimeError as exc:
        print("  run 1 raised:", exc)
    budget = session.state.get("_function_invocation_budget_state") or {}
    print("  budget left in session:", {k: budget[k] for k in ("attempt_count", "total_function_calls") if k in budget})
    calls_before = len(client.tool_choices)
    response = await run("look it up again")
    print("  run 2 tool_choice per provider call:", client.tool_choices[calls_before:])
    print("  tools executed:", executed)
    print("  run 2 text:", repr(response.text))

asyncio.run(main(stream=False))
asyncio.run(main(stream=True))
