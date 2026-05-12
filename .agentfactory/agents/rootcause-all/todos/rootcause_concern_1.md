# Concern #1 Investigation: FunctionTool.__call__ executes sync functions directly on event loop thread

**Investigated by**: Sub-agent
**Date**: 2026-05-12

## Verdict: VALIDATED

## Summary

The `FunctionTool.__call__` method (line 511 of `_tools.py`) executes the wrapped function synchronously and directly on the calling thread, with no thread offloading whatsoever. When this method is called from the `invoke()` async method (lines 682-683 and 733-734), a synchronous function runs directly on the event loop thread. The only protection is a post-hoc `await` if the result happens to be awaitable -- but for sync functions that block (e.g., `time.sleep(120)`, file I/O, network calls), the event loop is fully blocked for the duration. This is in stark contrast to `FunctionExecutor` in the workflows module, which explicitly uses `asyncio.to_thread()` for sync functions.

## 5-Whys Analysis

### Why 1: Why does a sync tool function block the event loop?
Because `FunctionTool.__call__` (file: `python/packages/core/agent_framework/_tools.py:511-538`) calls the wrapped function directly with `func(*args, **kwargs)` (line 535) or `func(self._instance, *args, **kwargs)` (line 534). There is no check for whether `func` is synchronous or asynchronous -- it simply calls it.

### Why 2: Why does `__call__` not offload sync functions to a thread?
Because `__call__` has no concept of sync vs async distinction. It does not inspect whether the function is a coroutine function. It returns whatever the function returns -- if async, a coroutine; if sync, the raw value. The async/sync differentiation is deferred to `invoke()`.

### Why 3: Why doesn't `invoke()` offload sync functions to a thread before calling `__call__`?
Because `invoke()` (file: `python/packages/core/agent_framework/_tools.py:562-767`) uses this pattern at lines 682-683 and 733-734:
```python
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res
```
This calls `__call__` first (synchronously on the event loop thread), and only then checks if the result is awaitable. For a sync function, `__call__` has already executed and returned by the time `inspect.isawaitable(res)` evaluates to `False`. The blocking has already occurred.

### Why 4: Why wasn't thread offloading added for sync functions in FunctionTool?
The codebase demonstrates awareness of this pattern -- `FunctionExecutor` (file: `python/packages/core/agent_framework/_workflows/_function_executor.py:131-151`) explicitly checks `inspect.iscoroutinefunction(func)` at construction time and wraps sync functions with `asyncio.to_thread()`:
```python
# Sync function without context - wrap to make async and ignore context using thread pool
async def wrapped_func(message: Any, ctx: WorkflowContext[Any]) -> Any:
    return await asyncio.to_thread(func, message)
```
However, `FunctionTool` was designed earlier (or independently) and never received this protection. The `__call__` / `invoke()` split appears designed primarily for the awaitable-coroutine case (async tool functions return coroutines that get awaited), not for protecting the event loop from blocking sync code.

### Why 5: Why is this especially dangerous in the agent auto-invocation loop?
Because the auto-invocation path uses `asyncio.gather()` at line 1769-1771:
```python
execution_results = await asyncio.gather(*[
    invoke_with_termination_handling(function_call, seq_idx)
    for seq_idx, function_call in enumerate(function_calls)
])
```
While `asyncio.gather()` enables concurrent execution of multiple tool calls, if any single tool is a blocking sync function, it blocks the entire event loop thread. This means:
1. All other concurrent tool calls in the same gather are stalled
2. The Responses API polling loop cannot receive streaming events
3. The entire agent framework becomes unresponsive for the duration of the blocking call

## Evidence Gathered

| # | Evidence | Location | Finding |
|---|----------|----------|---------|
| 1 | `FunctionTool.__call__` implementation | `_tools.py:511-538` | Calls `func(*args, **kwargs)` directly with no thread offloading; no `inspect.iscoroutinefunction` check |
| 2 | `invoke()` async method | `_tools.py:682-683, 733-734` | Pattern `res = self.__call__(**call_kwargs); result = await res if inspect.isawaitable(res) else res` -- blocking happens before the awaitable check |
| 3 | No `run_in_executor` or `asyncio.to_thread` in `_tools.py` | `_tools.py` (entire file) | `grep -n "run_in_executor\|asyncio.to_thread\|ThreadPool\|thread" _tools.py` returns zero matches |
| 4 | `FunctionExecutor` correctly offloads sync functions | `_function_executor.py:131-151` | Uses `asyncio.to_thread(func, message)` for sync functions, with explicit `inspect.iscoroutinefunction()` check at line 121 |
| 5 | Other modules use `asyncio.to_thread` for I/O | `_sessions.py:1008,1036`, `_skills.py:248,252`, `_harness/_todo.py:339,369` | Multiple modules in the same codebase correctly use `asyncio.to_thread()` for blocking operations |
| 6 | Auto-invocation uses `asyncio.gather` | `_tools.py:1769-1771` | All tool calls in a single iteration are gathered concurrently -- a single blocking sync tool stalls them all |
| 7 | `FunctionTool` constructor stores `func` with no wrapping | `_tools.py:297-339` | No `iscoroutinefunction` check, no thread wrapping at construction time |
| 8 | `FunctionExecutor` test validates thread execution | `tests/workflow/test_function_executor.py:480-504` | Tests confirm sync functions run in separate thread via `asyncio.to_thread` in FunctionExecutor |

## Conclusion

This concern is **VALIDATED**. The `FunctionTool.__call__` method executes synchronous functions directly on the event loop thread with zero thread offloading. The `invoke()` method's `inspect.isawaitable()` check only handles the case where the wrapped function is a coroutine (async def) -- it does not protect against blocking synchronous code. This is a design gap: the `FunctionExecutor` in the workflows module solves this exact problem with `asyncio.to_thread()`, but `FunctionTool` -- which is the primary tool mechanism for agents -- lacks this protection entirely. Any `@tool`-decorated synchronous function that performs blocking I/O (network requests, file operations, `time.sleep`, subprocess calls) will block the entire async event loop, preventing Responses API polling, concurrent tool execution, and all other async operations.
