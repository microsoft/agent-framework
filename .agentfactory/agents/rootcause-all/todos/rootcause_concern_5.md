# Concern #5 Investigation: ResponsesHostServer runs agent on same event loop as polling

**Investigated by**: Sub-agent
**Date**: 2026-05-12

## Verdict: VALIDATED

## Summary

The concern is validated. `ResponsesHostServer._handle_inner_agent` calls `agent.run()` using `await` on the same event loop that services HTTP requests (including polling). When a synchronous tool blocks the event loop thread inside `agent.run()`, it prevents all other async activity on that loop -- including any concurrent HTTP request handling, SSE streaming, health checks, and ASGI request processing.

The root cause is that `FunctionTool.invoke()` calls sync tools directly on the event loop thread without offloading to a thread pool, and there is no architectural isolation between tool execution and server request handling.

## 5-Whys Analysis

### Why 1: Why does a blocking sync tool affect Responses API handling?

Because `ResponsesHostServer._handle_response()` (line 278-288) awaits `_handle_inner_agent()`, which in turn awaits `self._agent.run()` (line 322 for non-streaming, line 341 for streaming). The entire agent execution, including all tool calls, runs as a coroutine on the ASGI server's event loop.

**Evidence**: `_responses.py:322`:
```python
response = await self._agent.run(stream=False, **run_kwargs)
```

### Why 2: Why does agent.run() block the event loop when a sync tool runs?

Because `agent.run()` (in `_agents.py:889-967`) delegates to `self._call_chat_client()` which calls `client.get_response()`. The `FunctionInvocationLayer.get_response()` implements a tool-calling loop (`_tools.py:2376-2498`) that awaits tool execution. The tool invocation calls `FunctionTool.invoke()` which directly calls the sync function on the event loop thread.

**Evidence**: `_tools.py:682-683` (in `FunctionTool.invoke()`):
```python
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res
```

If the tool function is synchronous, `self.__call__()` returns a non-awaitable result. The call executes synchronously on the current thread -- the event loop thread -- blocking it completely.

### Why 3: Why doesn't the framework offload sync tool functions to a thread pool?

The `FunctionTool.invoke()` method uses a simple `inspect.isawaitable()` check (line 683) to decide whether to `await` or use the result directly. There is no `asyncio.to_thread()` or `loop.run_in_executor()` wrapping for synchronous tool functions in the agent tool invocation path.

This contrasts with the **workflow** path where `FunctionExecutor` (`_function_executor.py:137-151`) explicitly wraps sync functions with `asyncio.to_thread()`:
```python
async def wrapped_func(message: Any, ctx: WorkflowContext[Any]) -> Any:
    return await asyncio.to_thread(func, message, ctx)
```

The agent tool path does not have this protection.

### Why 4: Why is there no isolation between tool execution and the ASGI server?

The `ResponsesHostServer` extends `ResponsesAgentServerHost` (an ASGI application from `azure.ai.agentserver`). The response handler is registered via `self.response_handler(self._handle_response)` (line 276). This handler is invoked as a coroutine within the ASGI request/response cycle. There is:
- No separate event loop for agent execution
- No dedicated thread pool for tool invocation
- No `asyncio.to_thread()` wrapping of `agent.run()`
- No task isolation or cancellation boundary

The ASGI server (Starlette-based, running on Hypercorn) runs `_handle_response` as part of an HTTP request handler coroutine. When this coroutine blocks, the entire ASGI server's event loop stalls.

### Why 5: Why does this matter for the Responses API specifically?

The Responses API uses a pattern where:
1. A client POSTs to `/responses` to start agent execution
2. For streaming, the server sends SSE events back as the agent produces output
3. For non-streaming, the server must complete the full agent run before responding
4. Health/readiness checks run on the same ASGI app

If a sync tool blocks the event loop:
- **Non-streaming**: The HTTP response cannot be sent until the tool unblocks
- **Streaming**: SSE event emission freezes; the client may time out
- **Health checks**: The readiness endpoint becomes unresponsive, potentially causing the hosting infrastructure to kill the container
- **Concurrent requests**: All other requests to the server are blocked

## Evidence Gathered

### Evidence 1: _handle_inner_agent awaits agent.run() directly
File: `python/packages/foundry_hosting/agent_framework_foundry_hosting/_responses.py`
Lines 290-334. Both streaming (line 341) and non-streaming (line 322) paths use `await` on the same event loop.

### Evidence 2: FunctionTool.invoke() runs sync tools on event loop thread
File: `python/packages/core/agent_framework/_tools.py`
Lines 682-683 (non-observability path) and lines 733-734 (observability path):
```python
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res
```
No `asyncio.to_thread()` or `run_in_executor()` wrapping exists for sync tool functions.

### Evidence 3: Tool calls run via asyncio.gather but still on same loop
File: `python/packages/core/agent_framework/_tools.py`
Line 1769:
```python
execution_results = await asyncio.gather(*[
    invoke_with_termination_handling(function_call, seq_idx) ...
])
```
`asyncio.gather` provides concurrency for multiple tool calls but they all run on the same event loop. A blocking sync call in any one of them blocks the loop.

### Evidence 4: Workflow path has protection, agent path does not
File: `python/packages/core/agent_framework/_workflows/_function_executor.py`
Lines 137-151 show explicit `asyncio.to_thread()` wrapping for sync workflow functions. This protection does not exist in the agent tool invocation path (`_tools.py:FunctionTool.invoke()`).

### Evidence 5: Server is a standard ASGI app with no isolation
File: `python/packages/foundry_hosting/agent_framework_foundry_hosting/_responses.py`
Line 208: `class ResponsesHostServer(ResponsesAgentServerHost):`
Line 276: `self.response_handler(self._handle_response)`

The base class comes from `azure-ai-agentserver-responses` which depends on `azure-ai-agentserver-core` which in turn depends on `hypercorn` and `starlette` (confirmed in `python/uv.lock:1126`). The server runs as a single-threaded asyncio ASGI application.

### Evidence 6: No thread pool or separate event loop anywhere in foundry_hosting
Search for `to_thread`, `run_in_executor`, `ThreadPool`, `thread_pool` in the foundry_hosting package returns zero results in `_responses.py`. The only threading-related code is in `FileBasedFunctionApprovalStorage` (lines 155, 202, 205) which correctly uses `asyncio.to_thread` for file I/O -- but this pattern is not applied to tool execution.

## Conclusion

The concern is **VALIDATED**. `ResponsesHostServer._handle_inner_agent` runs `agent.run()` directly on the ASGI server's event loop with no isolation. When the agent invokes a synchronous tool via `FunctionTool.invoke()`, the tool function executes synchronously on the event loop thread, blocking all concurrent async operations including HTTP request handling, SSE streaming, and health checks.

The architectural gap is clear: the workflow path (`FunctionExecutor`) correctly wraps sync functions with `asyncio.to_thread()`, but the agent tool path (`FunctionTool.invoke()`) does not. Additionally, the hosting server itself does not provide any isolation layer (separate thread, separate event loop, or `asyncio.to_thread` wrapping of `agent.run()`).

Two complementary fixes would address this:
1. **Tool-level**: Wrap sync tool functions with `asyncio.to_thread()` in `FunctionTool.invoke()` (matching the pattern already used in `FunctionExecutor`)
2. **Server-level**: Run `agent.run()` in an isolated context (e.g., via `asyncio.to_thread` or a dedicated executor) within `ResponsesHostServer._handle_inner_agent`
