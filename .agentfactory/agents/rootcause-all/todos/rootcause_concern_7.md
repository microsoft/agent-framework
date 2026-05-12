# Concern #7 Investigation: No test coverage for sync-blocking scenario

**Investigated by**: Sub-agent
**Date**: 2026-05-12

## Verdict: VALIDATED

## Summary

There are zero tests in test_tools.py or test_tools_future_annotations.py that verify sync FunctionTool functions do not block the asyncio event loop. The FunctionTool.invoke() method calls sync functions directly on the event loop thread without using asyncio.to_thread(), and no test exercises or validates this behavior. The only file that even mentions the scenario is test_function_executor.py (for the workflow system), but even that test is incomplete -- it checks metadata flags rather than actually proving non-blocking behavior.

## Evidence Gathered

### 1. test_tools.py -- No sync-blocking tests

Reviewed all 1,466 lines. The file contains tests for:
- Tool decorator behavior (sync and async)
- Schema validation and serialization
- Telemetry/OTEL span recording
- Input parsing
- FunctionInvocationContext injection
- Skip-parsing behavior
- Tool normalization/flattening

Key observations:
- `test_tool_decorator_with_async` (line 283) tests async tool creation but does NOT verify it runs without blocking the event loop.
- `test_tool_invoke_telemetry_async_function` (line 702) tests telemetry on an async tool but does NOT verify non-blocking behavior.
- Multiple sync tool tests (e.g., `test_tool_decorator` at line 40) test correctness of sync tool invocation but never verify they don't block the event loop.
- No test uses `asyncio.to_thread`, `time.sleep` (for blocking simulation), `threading.get_ident()`, or any event loop blocking detection.

### 2. test_tools_future_annotations.py -- No sync-blocking tests

Reviewed all 135 lines. This file focuses exclusively on PEP 563 (from __future__ import annotations) compatibility:
- FunctionInvocationContext parameter exclusion under PEP 563
- Optional type resolution
- Forward reference fallback

No tests related to sync blocking or event loop behavior.

### 3. test_function_executor.py -- Incomplete coverage

The workflow's FunctionExecutor has a test `test_sync_function_thread_execution` (line 477) that is explicitly named for this scenario, but it is INCOMPLETE. The test:
- Creates a sync executor with `time.sleep(0.01)` (line 490)
- Checks `_is_async` and `_has_context` metadata flags (lines 499-500)
- Contains this revealing comment (line 502-503): "The actual thread execution test would require a full workflow setup, but the important thing is that asyncio.to_thread is used in the wrapper"
- Does NOT actually run the function through the event loop to verify non-blocking behavior
- Does NOT verify the function runs on a different thread from the event loop thread
- The `execution_thread_id` variable (line 483) is set up but never actually asserted against

### 4. Source code analysis -- FunctionTool.invoke() does NOT use asyncio.to_thread

The FunctionTool.invoke() method in `_tools.py` (lines 682-683 and 733-734) executes functions as:
```python
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res
```
This means sync functions are called directly on the event loop thread. There is no `asyncio.to_thread()` wrapper for sync FunctionTools, unlike the workflow FunctionExecutor which does use `asyncio.to_thread()` (lines 139 and 151 of `_function_executor.py`).

### 5. Broader search -- No relevant tests anywhere

Searched all files under `python/packages/core/tests/` for:
- `asyncio.to_thread` -- Found only in `test_sessions.py` (for file I/O, unrelated to tools)
- `time.sleep` -- Found only in `test_sessions.py` (for concurrent write testing) and `test_function_executor.py` (incomplete test above)
- `event.loop` / `blocking` / `_is_async` -- No relevant hits in tool test files

## Conclusion

This concern is VALIDATED on two levels:

1. **Missing test coverage**: There is no test anywhere in the test suite that verifies sync FunctionTool functions do not block the event loop. The closest test (`test_sync_function_thread_execution` in test_function_executor.py) is for the workflow FunctionExecutor (not FunctionTool) and is itself incomplete -- it only checks metadata flags without actually executing the function through an async context.

2. **Underlying bug confirmed by source analysis**: The FunctionTool.invoke() method in `_tools.py` does NOT use `asyncio.to_thread()` for sync functions. It calls them directly on the event loop thread via `self.__call__()`. This is in contrast to the workflow FunctionExecutor which correctly uses `asyncio.to_thread()`. A test for this scenario would immediately reveal the blocking behavior as a bug.

### Files examined:
- `/python/packages/core/tests/core/test_tools.py` -- 1,466 lines, zero sync-blocking tests
- `/python/packages/core/tests/core/test_tools_future_annotations.py` -- 135 lines, zero sync-blocking tests
- `/python/packages/core/tests/workflow/test_function_executor.py` -- 968 lines, one incomplete sync-blocking test
- `/python/packages/core/agent_framework/_tools.py` -- FunctionTool.invoke() confirmed to NOT use asyncio.to_thread()
- `/python/packages/core/agent_framework/_workflows/_function_executor.py` -- FunctionExecutor confirmed to correctly use asyncio.to_thread()
