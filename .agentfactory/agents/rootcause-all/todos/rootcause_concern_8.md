# Concern #8 Investigation: asyncio.to_thread() pattern not applied to FunctionTool

**Investigated by**: Sub-agent
**Date**: 2026-05-12

## Verdict: VALIDATED

## Summary

FunctionExecutor in `_function_executor.py` explicitly detects sync vs async functions using `inspect.iscoroutinefunction()` and wraps synchronous functions with `asyncio.to_thread()` to avoid blocking the event loop. FunctionTool in `_tools.py` has no such mechanism -- it calls synchronous functions directly on the event loop thread via `self.__call__()`, then checks `inspect.isawaitable(res)` on the return value. For sync functions, `isawaitable` returns False and the result is used directly, meaning the blocking call already completed on the event loop thread. This is particularly dangerous because multiple tool calls are executed concurrently via `asyncio.gather()`, so one blocking sync tool will stall all other concurrent tool executions.

## 5-Whys Analysis

### Why 1: Why does FunctionTool block the event loop when calling sync functions?
Because `FunctionTool.invoke()` calls `self.__call__(**call_kwargs)` which directly invokes the wrapped function synchronously. The result is then checked with `inspect.isawaitable(res)` -- but for sync functions, this check happens AFTER the blocking call has already completed.

**Evidence**: `_tools.py:682-683`:
```python
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res
```
And `_tools.py:733-734` (same pattern in the observability branch):
```python
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res
```

### Why 2: Why doesn't FunctionTool detect whether the wrapped function is sync or async?
Because FunctionTool's `__init__` never inspects the function with `inspect.iscoroutinefunction()` and stores no `_is_async` flag. It has no sync/async awareness at construction time.

**Evidence**: `_tools.py:297-404` -- the entire `__init__` method stores `self.func = func` at line 373 but never checks `inspect.iscoroutinefunction(func)`. Compare with `_function_executor.py:122`:
```python
self._is_async = inspect.iscoroutinefunction(func)
```

### Why 3: Why doesn't FunctionTool wrap sync functions with asyncio.to_thread()?
Because FunctionTool relies on a post-hoc `isawaitable` check on the return value rather than a pre-call decision based on function type. The `isawaitable` pattern cannot prevent blocking -- it only determines how to handle the already-computed result.

**Evidence**: FunctionExecutor wraps sync functions proactively at construction time (`_function_executor.py:136-151`):
```python
elif self._has_context and not self._is_async:
    async def wrapped_func(message, ctx):
        return await asyncio.to_thread(func, message, ctx)
...
else:
    async def wrapped_func(message, ctx):
        return await asyncio.to_thread(func, message)
```

FunctionTool has no equivalent wrapping anywhere in its code.

### Why 4: Why was this pattern not applied to FunctionTool when it was applied to FunctionExecutor?
FunctionTool predates FunctionExecutor significantly. FunctionTool evolved from the original tool infrastructure (earliest commits circa 2024, commit `3449902b`), while FunctionExecutor was added much later (commit `ed8461aa`, September 2025) specifically with async-safety built in from the start. The two components were developed by different authors at different times in different subsystems (tools vs. workflows), and the improvement was never backported.

### Why 5: Why is this a real problem and not just theoretical?
Because the framework executes multiple tool calls concurrently using `asyncio.gather()` (`_tools.py:1769`):
```python
execution_results = await asyncio.gather(*[
    invoke_with_termination_handling(function_call, seq_idx)
    for seq_idx, function_call in enumerate(function_calls)
])
```
If any tool wraps a sync function that does I/O (file reads, HTTP calls, database queries), it blocks the entire event loop, preventing all other concurrent tool invocations from progressing. This defeats the purpose of `asyncio.gather()` parallelism.

## Evidence Gathered

### FunctionExecutor (correct pattern)
- **File**: `python/packages/core/agent_framework/_workflows/_function_executor.py`
- **Line 122**: `self._is_async = inspect.iscoroutinefunction(func)` -- detects async at init
- **Lines 132-151**: Four-way branching based on `_is_async` and `_has_context`, wrapping sync functions with `asyncio.to_thread()` in both cases (with and without context)
- **Imports**: `import asyncio` at line 18, `import inspect` at line 19

### FunctionTool (missing pattern)
- **File**: `python/packages/core/agent_framework/_tools.py`
- **Line 373**: `self.func = func` -- stores function without any async detection
- **No `_is_async` attribute** exists on FunctionTool
- **No `asyncio.to_thread` usage** for tool function invocation (only used at line 1769 for `asyncio.gather`)
- **Line 5**: `import asyncio` is present but only used for `asyncio.gather` in the function invocation loop
- **Lines 682-683, 733-734**: `isawaitable` check happens AFTER the sync call completes -- too late to prevent blocking

### The @tool decorator
- **File**: `_tools.py:1305-1325`
- The `@tool` decorator creates a `FunctionTool` directly, passing through the user's function without any async wrapping
- Both sync and async functions are accepted (documented in examples at lines 1242-1272), but sync functions get no thread offloading

### Parallel execution path
- **File**: `_tools.py:1769-1771`
- Multiple tool calls are dispatched concurrently via `asyncio.gather()`
- Each tool call eventually reaches `tool.invoke()` which calls `self.__call__()` synchronously for sync tools
- A single blocking sync tool will serialize what should be parallel execution

### No historical justification found
- `git log --all --oneline --grep="to_thread" -- python/packages/core/agent_framework/_tools.py` returned zero results
- No comments in the code explain why `asyncio.to_thread()` is not used
- No commits reference a deliberate decision to exclude thread offloading from FunctionTool

## Conclusion

This concern is **VALIDATED**. The `asyncio.to_thread()` pattern correctly implemented in `FunctionExecutor` (`_function_executor.py:136-151`) was never applied to `FunctionTool` (`_tools.py`). FunctionTool calls sync functions directly on the event loop thread, which blocks the event loop and defeats `asyncio.gather()` parallelism when multiple tools are invoked concurrently. This is not a theoretical issue -- it affects any user who defines a sync tool function that performs I/O operations (the common case, given that the `@tool` decorator documentation shows sync function examples as the primary usage pattern). The fix would be to detect `inspect.iscoroutinefunction(self.func)` at construction time and wrap sync functions with `asyncio.to_thread()` in the `invoke()` method, mirroring the FunctionExecutor approach.
