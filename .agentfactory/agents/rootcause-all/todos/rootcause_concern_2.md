# Concern #2 Investigation: FunctionTool.invoke() non-observability code path blocks at line 682

**Investigated by**: Sub-agent (rootcause-all)
**Date**: 2026-05-12

## Verdict: VALIDATED

## Summary

The `FunctionTool.invoke()` method at line 682 of `_tools.py` calls `self.__call__(**call_kwargs)` synchronously on the event loop. For synchronous (non-async) tool functions, this call blocks the entire async event loop until the function returns. The subsequent `await res if inspect.isawaitable(res) else res` on line 683 does NOT prevent blocking -- it only helps for async functions that return awaitables. The blocking occurs during the `self.__call__()` call itself, before line 683 is even reached. Both the non-observability path (line 682) and the observability path (line 733) share this identical defect. This is compounded by the fact that multiple tool calls are dispatched concurrently via `asyncio.gather` (line 1769), meaning a single blocking synchronous tool will stall all concurrent tool executions.

## 5-Whys Analysis

### Why #1: Why does line 682 block the event loop?

Because `self.__call__(**call_kwargs)` (line 682) is a regular synchronous method call. When the wrapped function (`self.func`) is a synchronous Python function, it executes entirely on the current thread -- the event loop thread. No coroutine is created; no thread offloading occurs. The call completes synchronously before execution proceeds to line 683.

**Evidence** (`_tools.py:511-535`):
```python
def __call__(self, *args: Any, **kwargs: Any) -> Any:
    """Call the wrapped function with the provided arguments."""
    # ... guard checks ...
    self.invocation_count += 1
    try:
        func = self.func
        if func is None:
            raise ToolException(...)
        if self._instance is not None:
            return func(self._instance, *args, **kwargs)
        return func(*args, **kwargs)  # <-- direct synchronous call
    except Exception:
        self.invocation_exception_count += 1
        raise
```

The `__call__` method calls `func()` directly. For a synchronous function, this returns a plain value, not an awaitable. The blocking happens here.

### Why #2: Why doesn't the `await res if inspect.isawaitable(res) else res` on line 683 prevent blocking?

Because `inspect.isawaitable(res)` only checks whether the *return value* is awaitable. For a synchronous function, `res` is already the final computed result (a plain value like a string, dict, etc.), not a coroutine. The `else res` branch executes, which is a no-op -- it just passes the already-computed value through. The blocking already happened on line 682 during `self.__call__()`.

**Evidence** (`_tools.py:682-683`):
```python
res = self.__call__(**call_kwargs)           # line 682: blocks HERE for sync functions
result = await res if inspect.isawaitable(res) else res  # line 683: too late, blocking already done
```

The `isawaitable` check is only useful for async functions where `__call__` returns a coroutine object (which is fast/non-blocking), and the actual work happens during the `await`.

### Why #3: Why doesn't `invoke()` offload synchronous functions to a thread?

Because neither `invoke()` nor `__call__()` contains any `asyncio.to_thread()`, `loop.run_in_executor()`, or equivalent thread-offloading mechanism. A grep for `run_in_executor` and `to_thread` in `_tools.py` returns zero results.

**Evidence**: `grep -rn 'run_in_executor\|to_thread' _tools.py` produces no matches.

This is in contrast to `FunctionExecutor` in `_workflows/_function_executor.py` (lines 137-151), which explicitly wraps synchronous functions with `asyncio.to_thread()`:

```python
# From _function_executor.py:137-151
elif self._has_context and not self._is_async:
    async def wrapped_func(message, ctx):
        return await asyncio.to_thread(func, message, ctx)  # correct pattern
else:
    async def wrapped_func(message, ctx):
        return await asyncio.to_thread(func, message)  # correct pattern
```

The workflow subsystem correctly identifies and handles sync functions. The tool subsystem does not.

### Why #4: Why is this especially harmful in practice?

Because multiple tool calls from a single model response are executed concurrently via `asyncio.gather` at line 1769:

```python
execution_results = await asyncio.gather(*[
    invoke_with_termination_handling(function_call, seq_idx)
    for seq_idx, function_call in enumerate(function_calls)
])
```

If even one of those concurrent tool invocations wraps a blocking synchronous function, it blocks the event loop thread. This prevents all other concurrent coroutines (including other tool invocations in the same `gather`, network I/O, heartbeats, timeouts) from making progress. The concurrency promised by `asyncio.gather` becomes illusory.

### Why #5: Why was this not caught or designed differently?

The `isawaitable` pattern on line 683 suggests the authors were aware that both sync and async functions could be wrapped, but used a pattern that only handles the *return value* rather than the *execution* of synchronous functions. The correct pattern (used in `_function_executor.py`) is to check `inspect.iscoroutinefunction(func)` at registration time and wrap synchronous functions with `asyncio.to_thread()`. The `FunctionTool` class does not perform this check or wrapping anywhere in its initialization or invocation path.

## Evidence Gathered

### 1. The blocking call site (both code paths are identical)

**Non-observability path** (`_tools.py:679-683`):
```python
if not OBSERVABILITY_SETTINGS.ENABLED:
    logger.info(f"Function name: {self.name}")
    logger.debug(f"Function arguments: {observable_kwargs}")
    res = self.__call__(**call_kwargs)           # BLOCKS for sync functions
    result = await res if inspect.isawaitable(res) else res  # too late
```

**Observability path** (`_tools.py:733-734`):
```python
    res = self.__call__(**call_kwargs)           # BLOCKS for sync functions
    result = await res if inspect.isawaitable(res) else res  # too late
```

### 2. __call__ performs direct synchronous invocation (`_tools.py:529-535`)
```python
func = self.func
if func is None:
    raise ToolException(...)
if self._instance is not None:
    return func(self._instance, *args, **kwargs)
return func(*args, **kwargs)
```

### 3. No thread offloading exists in _tools.py

Zero occurrences of `run_in_executor`, `to_thread`, `ThreadPoolExecutor`, or `ProcessPoolExecutor` in the entire 2673+ line `_tools.py` file.

### 4. Correct pattern exists in the same codebase (`_function_executor.py:8-9, 137-151`)

The `FunctionExecutor` class documents and implements the correct pattern:
> "Synchronous functions are executed in a thread pool using asyncio.to_thread() to avoid blocking the event loop."

### 5. Concurrent tool dispatch via asyncio.gather (`_tools.py:1769-1771`)
```python
execution_results = await asyncio.gather(*[
    invoke_with_termination_handling(function_call, seq_idx)
    for seq_idx, function_call in enumerate(function_calls)
])
```

This makes the blocking problem worse: a single blocking sync tool stalls all concurrent tool executions.

### 6. @tool decorator accepts both sync and async functions (`_tools.py:1267-1272`)
```python
# Async functions are also supported
@tool(approval_mode="never_require")
async def async_get_weather(location: str) -> str:
    '''Get weather asynchronously.'''
    return f"Weather in {location}"
```

The documentation says "also supported," implying sync functions are the primary/default use case, making the blocking problem likely to affect many users.

## Conclusion

**VALIDATED**. The concern is confirmed. `FunctionTool.invoke()` directly calls synchronous tool functions on the event loop thread at line 682 (and identically at line 733 in the observability path). The `await res if inspect.isawaitable(res) else res` check on line 683 is insufficient because it only handles the return value -- the blocking has already occurred during the `self.__call__()` invocation. There is no `asyncio.to_thread()` or `run_in_executor()` wrapping anywhere in `_tools.py`. The correct pattern (wrapping sync functions in `asyncio.to_thread()`) already exists in the same codebase in `_function_executor.py`, demonstrating both awareness of the problem and a proven fix. The impact is amplified by `asyncio.gather` at line 1769 which runs multiple tools concurrently -- a single blocking sync tool will stall all of them.

The fix would involve detecting synchronous functions (via `inspect.iscoroutinefunction`) and wrapping their execution in `asyncio.to_thread()` within the `invoke()` method, similar to what `FunctionExecutor` already does.
