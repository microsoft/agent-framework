# Concern #4 Investigation: No sync-to-async offloading in FunctionTool

**Investigated by**: Sub-agent
**Date**: 2026-05-12

## Verdict: VALIDATED

## Summary

FunctionTool does NOT offload synchronous functions to a thread pool. When a sync function is wrapped by FunctionTool, it is called directly on the event loop thread. The result is then checked with `inspect.isawaitable()` -- but a sync function never returns an awaitable, so the raw (already-computed) result is used as-is. This means any blocking sync function (I/O, CPU-intensive work) will block the entire asyncio event loop. By contrast, FunctionExecutor explicitly detects sync vs async functions at init time and wraps sync functions with `asyncio.to_thread()`.

## 5-Whys Analysis

**Why #1: Why does FunctionTool block the event loop when wrapping a sync function?**
Because `FunctionTool.__call__()` (`_tools.py:511`) calls `self.func(*args, **kwargs)` directly, with no thread offloading. The `invoke()` method (`_tools.py:682-683`) calls `self.__call__(**call_kwargs)` and then does `await res if inspect.isawaitable(res) else res`. For a sync function, `res` is never awaitable, so the blocking call has already completed on the event loop thread.

**Why #2: Why does FunctionTool not detect whether the wrapped function is sync or async?**
Because `FunctionTool.__init__()` (`_tools.py:297`) stores the function as `self.func = func` (line 373) but never inspects it with `inspect.iscoroutinefunction()` and never stores an `_is_async` flag. There is no sync-vs-async detection anywhere in FunctionTool's initialization.

**Why #3: Why does FunctionExecutor handle this correctly but FunctionTool does not?**
FunctionExecutor was designed with explicit awareness of the sync/async distinction. At `_function_executor.py:122`, it stores `self._is_async = inspect.iscoroutinefunction(func)`. Then at lines 132-151, it creates four distinct wrapper branches:
- async + context: direct pass-through
- sync + context: wraps with `asyncio.to_thread(func, message, ctx)`
- async + no context: wraps to ignore context
- sync + no context: wraps with `asyncio.to_thread(func, message)`

FunctionTool predates this design and was never updated to include the same offloading mechanism.

**Why #4: Why was FunctionTool not updated when FunctionExecutor got this capability?**
FunctionTool and FunctionExecutor serve different purposes in the architecture -- FunctionTool wraps functions as model-callable tools, while FunctionExecutor wraps functions as workflow executors. They were developed independently and the sync-offloading pattern was not back-ported to FunctionTool.

**Why #5: Why is this a problem in practice?**
Because any user who registers a sync function as a tool (which is the most natural thing to do -- e.g., file I/O, HTTP calls, database queries) will block the event loop whenever the model invokes that tool. This prevents concurrent tool execution (the framework uses `asyncio.gather` at `_tools.py:1769` for parallel tool calls), degrades responsiveness, and can cause timeouts in production systems.

## Evidence Gathered

### Evidence 1: FunctionTool.__call__ does NOT offload sync functions
File: `python/packages/core/agent_framework/_tools.py`, lines 511-538

```python
def __call__(self, *args: Any, **kwargs: Any) -> Any:
    """Call the wrapped function with the provided arguments."""
    # ...validation checks...
    self.invocation_count += 1
    try:
        func = self.func
        if func is None:
            raise ToolException(f"Function '{self.name}' has no implementation.")
        # If we have a bound instance, call the function with self
        if self._instance is not None:
            return func(self._instance, *args, **kwargs)
        return func(*args, **kwargs)     # <-- DIRECT CALL, no thread offloading
    except Exception:
        self.invocation_exception_count += 1
        raise
```

### Evidence 2: FunctionTool.invoke uses isawaitable check but no preemptive offloading
File: `python/packages/core/agent_framework/_tools.py`, lines 682-683 (non-observability path) and 733-734 (observability path)

```python
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res
```

The `inspect.isawaitable(res)` check only handles the case where the wrapped function itself is async (returns a coroutine). It does NOT offload sync functions to a thread -- the sync function has already executed and blocked the event loop by the time this check runs.

### Evidence 3: FunctionTool.__init__ does NOT store _is_async flag
File: `python/packages/core/agent_framework/_tools.py`, lines 297-404

The entire `__init__` method stores `self.func = func` at line 373 but never calls `inspect.iscoroutinefunction(func)` and never creates any `_is_async` attribute.

### Evidence 4: FunctionExecutor DOES detect and offload sync functions
File: `python/packages/core/agent_framework/_workflows/_function_executor.py`, lines 122-151

```python
# Determine if the function is an async function
self._is_async = inspect.iscoroutinefunction(func)

# ...then four branches:
if self._has_context and self._is_async:
    wrapped_func = func  # direct pass-through
elif self._has_context and not self._is_async:
    async def wrapped_func(message, ctx):
        return await asyncio.to_thread(func, message, ctx)  # OFFLOADED
elif not self._has_context and self._is_async:
    async def wrapped_func(message, ctx):
        return await func(message)
else:
    async def wrapped_func(message, ctx):
        return await asyncio.to_thread(func, message)  # OFFLOADED
```

### Evidence 5: No asyncio.to_thread usage in FunctionTool
A grep for `to_thread` and `iscoroutinefunction` in `_tools.py` returns zero matches. The only `asyncio` import at line 5 is used solely for `asyncio.gather` at line 1769 (parallel tool execution), not for thread offloading.

### Evidence 6: Parallel tool execution is undermined
File: `python/packages/core/agent_framework/_tools.py`, line 1769

```python
execution_results = await asyncio.gather(*[
```

The framework attempts to execute multiple tool calls in parallel using `asyncio.gather`. But if any of those tools wrap sync functions, they block the event loop, serializing what should be concurrent execution.

## Conclusion

This concern is **VALIDATED**. FunctionTool lacks any sync-to-async offloading mechanism. Sync functions passed to FunctionTool are called directly on the event loop thread, blocking it for the duration of their execution. FunctionExecutor already solves this problem correctly using `inspect.iscoroutinefunction()` detection at init time and `asyncio.to_thread()` wrapping for sync functions. The same pattern should be applied to FunctionTool to prevent event loop blocking, especially since the framework relies on `asyncio.gather` for concurrent tool invocation.
