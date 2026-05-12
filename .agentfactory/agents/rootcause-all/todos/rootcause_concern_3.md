# Concern #3 Investigation: FunctionTool.invoke() observability code path blocks at line 733

**Investigated by**: Sub-agent
**Date**: 2026-05-12

## Verdict: VALIDATED

## Summary

The observability-enabled code path in `FunctionTool.invoke()` at line 733 of `_tools.py` suffers from the same event-loop-blocking behavior as the non-observability path at line 682. When a synchronous function is wrapped as a `FunctionTool`, calling `self.__call__(**call_kwargs)` executes it directly on the event loop thread. The `inspect.isawaitable()` check on line 734 only helps for async functions -- for sync functions, the blocking has already occurred by the time the check runs. Additionally, the observability path wraps this blocking call inside an OpenTelemetry span context manager and `perf_counter` timing, meaning any event-loop stall also inflates span duration and holds the span open, preventing other spans from being properly parented during the stall.

## 5-Whys Analysis

**Why #1**: Why does the observability code path block the event loop?
Because at line 733 (`_tools.py:733`), `res = self.__call__(**call_kwargs)` calls the wrapped function synchronously, directly on the current (event-loop) thread. There is no `await`, no `asyncio.to_thread()`, and no `run_in_executor()` call.

**Why #2**: Why is `self.__call__()` synchronous even in an `async def invoke()` method?
Because `FunctionTool.__call__()` (`_tools.py:511-538`) is a regular (non-async) method. It directly calls `self.func(...)` or `self.func(self._instance, ...)`. The return value may or may not be a coroutine, but the call itself always executes synchronously on the calling thread.

**Why #3**: Why doesn't the `inspect.isawaitable()` check on line 734 prevent blocking?
Because `inspect.isawaitable(res)` only checks whether the *return value* is awaitable (a coroutine object). For a synchronous function, the function body has already executed to completion by the time `res` is assigned. The blocking work happened during the `self.__call__()` call on line 733, not during the `await` on line 734. The `isawaitable` check is useful only for async functions that return coroutines.

**Why #4**: Why is this particularly concerning in the observability path?
Because the observability path wraps the blocking call inside:
- An OpenTelemetry span context (`with get_function_span(attributes=attributes) as span:` at line 725)
- A `perf_counter()` timing bracket (lines 730-735)
- Sensitive data logging conditionals (lines 728-729)

If the sync function blocks for a long time, the span remains open and active during the entire stall. This means: (a) span duration is inflated by the blocking time, (b) any other concurrent work that creates child spans during the stall would be incorrectly parented under this tool's span, and (c) the span's `end_on_exit=True` behavior (observability.py:1823) delays span export.

**Why #5**: Why wasn't `asyncio.to_thread()` or `run_in_executor()` used for sync functions?
The code uses a single pattern for both sync and async functions: call `self.__call__()`, then conditionally `await` if the result is awaitable. This pattern was likely chosen for simplicity but it fails to account for the event-loop-blocking nature of synchronous function execution. There is no detection of whether the wrapped function is sync vs async before the call, and no offloading mechanism for sync functions.

## Evidence Gathered

### Evidence 1: The non-observability path (lines 682-683)
```python
# _tools.py:682-683
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res
```
This is the baseline pattern. Same blocking issue, but without span/timing overhead.

### Evidence 2: The observability path (lines 725-767)
```python
# _tools.py:725-767
with get_function_span(attributes=attributes) as span:
    attributes[OtelAttr.MEASUREMENT_FUNCTION_TAG_NAME] = self.name
    logger.info(f"Function name: {self.name}")
    if OBSERVABILITY_SETTINGS.SENSITIVE_DATA_ENABLED:
        logger.debug(f"Function arguments: {serializable_kwargs}")
    start_time_stamp = perf_counter()
    end_time_stamp: float | None = None
    try:
        res = self.__call__(**call_kwargs)                          # <-- LINE 733: BLOCKS HERE
        result = await res if inspect.isawaitable(res) else res    # <-- LINE 734: too late for sync
        end_time_stamp = perf_counter()
    except Exception as exception:
        end_time_stamp = perf_counter()
        ...
    finally:
        duration = (end_time_stamp or perf_counter()) - start_time_stamp
        span.set_attribute(OtelAttr.MEASUREMENT_FUNCTION_INVOCATION_DURATION, duration)
        self._invocation_duration_histogram.record(duration, attributes=attributes)
```
The blocking `self.__call__()` at line 733 runs inside the span context and between `perf_counter()` calls. The span is held open for the entire duration of the sync function execution.

### Evidence 3: FunctionTool.__call__() is synchronous (lines 511-538)
```python
# _tools.py:511-538
def __call__(self, *args: Any, **kwargs: Any) -> Any:
    """Call the wrapped function with the provided arguments."""
    ...
    self.invocation_count += 1
    try:
        func = self.func
        if func is None:
            raise ToolException(f"Function '{self.name}' has no implementation.")
        if self._instance is not None:
            return func(self._instance, *args, **kwargs)
        return func(*args, **kwargs)
    except Exception:
        self.invocation_exception_count += 1
        raise
```
This is a plain `def` method. It calls `func(...)` directly. For sync functions, all work happens inline before returning.

### Evidence 4: get_function_span() uses end_on_exit=True (observability.py:1819-1825)
```python
# observability.py:1819-1825
def get_function_span(attributes):
    return get_tracer().start_as_current_span(
        name=f"{attributes[OtelAttr.OPERATION]} {attributes[OtelAttr.TOOL_NAME]}",
        attributes=attributes,
        set_status_on_exception=False,
        end_on_exit=True,
        record_exception=False,
    )
```
The span is set as the "current span" in OpenTelemetry context. It remains current throughout the blocking execution, meaning any instrumented code that runs during the stall (e.g., HTTP clients inside the sync function) would be incorrectly parented under this span.

### Evidence 5: No executor offloading anywhere in the file
```
$ grep -n 'run_in_executor\|to_thread' _tools.py
(no results)
```
There is no use of `asyncio.to_thread()` or `loop.run_in_executor()` anywhere in `_tools.py`. The entire file lacks any mechanism for offloading synchronous work to a thread pool.

## Conclusion

**VALIDATED**. The observability code path at line 733 of `_tools.py` blocks the event loop for synchronous functions in the same way as the non-observability path at line 682, but with the additional impact of holding an OpenTelemetry span open during the stall. The `inspect.isawaitable()` check on line 734 cannot prevent the blocking because it only examines the return value after the synchronous function has already completed execution. The fix would require detecting whether the wrapped function is sync (e.g., via `inspect.iscoroutinefunction(self.func)`) and offloading sync functions to a thread executor before entering the span timing bracket, or at minimum within it.
