# Concern #6 Investigation: MCP tool invocation path blocks

**Investigated by**: Sub-agent
**Date**: 2026-05-12

## Verdict: VALIDATED

## Summary

The MCP tool invocation path at `_agents.py:1543` calls `agent_tool.invoke()` in the same async context with no thread offloading, sharing the exact same blocking-vulnerable code path as the normal (non-MCP) tool invocation. When a synchronous tool function is invoked via the MCP server, the event loop is blocked during execution because `FunctionTool.invoke()` calls `self.__call__()` directly and only checks `inspect.isawaitable()` after the call returns -- meaning synchronous functions execute inline on the event loop thread.

## 5-Whys Analysis

### Why 1: Why does the MCP tool invocation path block?
Because `_agents.py:1543` calls `await agent_tool.invoke(arguments=args_instance)` directly in the MCP handler coroutine `_call_tool()`, which runs on the event loop.

**Evidence**: `_agents.py:1523-1543`:
```python
@server.call_tool()
async def _call_tool(
    name: str, arguments: dict[str, Any]
) -> Sequence[...]:
    ...
    result = await agent_tool.invoke(arguments=args_instance)
```

### Why 2: Why does `agent_tool.invoke()` block?
Because `FunctionTool.invoke()` at `_tools.py:682-683` calls `self.__call__(**call_kwargs)` synchronously and only conditionally awaits:
```python
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res
```
If `self.func` is a synchronous function, `__call__` executes it inline on the event loop thread before returning. The `isawaitable` check only helps if the function is already async.

**Evidence**: `_tools.py:511-535` (`__call__` method):
```python
def __call__(self, *args: **kwargs):
    ...
    func = self.func
    if self._instance is not None:
        return func(self._instance, *args, **kwargs)
    return func(*args, **kwargs)
```

### Why 3: Why is there no thread offloading for synchronous tool functions?
Because `FunctionTool.invoke()` was not designed with thread isolation. Unlike `_workflows/_function_executor.py` (which explicitly uses `asyncio.to_thread()` for sync functions at lines 139 and 151), the `FunctionTool` path has no such protection.

**Evidence**: Searching for `run_in_executor`, `to_thread`, and `ThreadPoolExecutor` in `_tools.py` yields zero results. The workflow `FunctionExecutor` at `_workflows/_function_executor.py:36-151` demonstrates the correct pattern:
```python
# Sync function with context - wrap to make async using thread pool
async def wrapped_func(message, ctx):
    return await asyncio.to_thread(func, message, ctx)
```
This pattern is completely absent from `FunctionTool`.

### Why 4: Why is the MCP path particularly affected?
Because the MCP server handler `_call_tool()` runs within the MCP server's event loop (via `server.run()` on the same asyncio loop), and when `agent_tool.invoke()` blocks, it blocks the entire MCP server from processing any other requests. The MCP server is typically a single-threaded async server (using stdio or streamable HTTP transport), so blocking the event loop freezes all MCP communication.

**Evidence**: `samples/02-agents/mcp/agent_as_mcp_server.py:73-74`:
```python
async with stdio_server() as (read_stream, write_stream):
    await server.run(read_stream, write_stream, server.create_initialization_options())
```

### Why 5: Why is this the same issue as the non-MCP path?
Because both the MCP path (`_agents.py:1543`) and the normal path (`_tools.py:1527, 1570`) call the same `FunctionTool.invoke()` method, which has the same lack of thread offloading. The root cause is in `FunctionTool.invoke()` itself, not in either caller.

**Evidence**: All three invocation sites call the same method:
- MCP path: `_agents.py:1543` -- `await agent_tool.invoke(arguments=args_instance)`
- Normal path (no middleware): `_tools.py:1527` -- `await tool.invoke(arguments=args, context=direct_context, ...)`
- Normal path (with middleware): `_tools.py:1570` -- `return await tool.invoke(arguments=context_obj.arguments, ...)`

## Evidence Gathered

### 1. MCP handler executes in the event loop
File: `python/packages/core/agent_framework/_agents.py:1523-1550`
The `_call_tool` handler is an `async def` registered with `@server.call_tool()`. It runs in the MCP server's event loop. The `agent_tool.invoke()` call at line 1543 is awaited directly with no isolation.

### 2. FunctionTool.invoke() runs sync functions inline
File: `python/packages/core/agent_framework/_tools.py:682-683`
```python
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res
```
For sync functions, `self.__call__()` executes the function completely before returning, blocking the event loop for the entire duration.

### 3. No thread offloading anywhere in FunctionTool
File: `python/packages/core/agent_framework/_tools.py`
A search for `run_in_executor`, `to_thread`, and `ThreadPoolExecutor` yields zero matches in this file. There is no mechanism to offload synchronous function execution to a thread pool.

### 4. Workflow FunctionExecutor has the fix but FunctionTool does not
File: `python/packages/core/agent_framework/_workflows/_function_executor.py:137-151`
The workflow system correctly detects sync functions and wraps them with `asyncio.to_thread()`. This pattern was not applied to `FunctionTool`.

### 5. MCP path uses `as_tool()` which creates an async wrapper
File: `python/packages/core/agent_framework/_agents.py:497,545-564`
The `as_tool()` method creates an `async def _agent_wrapper` that calls `self.run(stream=True)` and `await stream.get_final_response()`. Since the wrapper itself is async, the `isawaitable` check at `_tools.py:683` will correctly await it. **However**, this only applies when an Agent is exposed as an MCP server via `as_mcp_server()`. If a user registers a raw synchronous `FunctionTool` and exposes it differently, the blocking issue remains.

### 6. Nuance: as_mcp_server specifically wraps the agent
File: `python/packages/core/agent_framework/_agents.py:1497`
```python
agent_tool = self.as_tool(name=self._get_agent_name())
```
The `as_mcp_server()` method converts the entire agent into a single tool using `as_tool()`, which creates an async wrapper. This means the specific `as_mcp_server()` path is **not directly blocking** because the tool function is async. However, the underlying `FunctionTool.invoke()` still lacks thread offloading as a general mechanism, and any sub-tools within the agent that are synchronous will block when the agent runs them during its `self.run()` call.

## Conclusion

**VALIDATED** -- The MCP tool invocation path at `_agents.py:1543` calls the same `FunctionTool.invoke()` method that lacks thread offloading for synchronous functions. While the specific `as_mcp_server()` path mitigates direct blocking by wrapping the agent in an async function, the underlying issue persists:

1. `FunctionTool.invoke()` has no thread offloading for sync functions (unlike `FunctionExecutor` in the workflow system).
2. Any synchronous tools registered on the agent will block the event loop when invoked during the agent's `run()` call, which is triggered from the MCP handler.
3. The MCP server is single-threaded async, so blocking the event loop freezes all MCP communication.

The root cause is shared with the non-MCP path: `FunctionTool.invoke()` at `_tools.py:682-683` executes synchronous functions inline on the event loop thread without offloading to a thread pool.
