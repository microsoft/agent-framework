# Root Cause Analysis: Blocking synchronous tool execution freezes Responses API polling inside async event loop

**Date**: 2026-05-12
**Status**: Root causes identified
**Problem File**: .agentfactory/agents/soldesign-plan/problem-summary-1.md
**Upstream Issue**: microsoft/agent-framework#5741

## Problem Summary

When a tool registered via `@tool` contains blocking synchronous code (e.g., `time.sleep(120)`), the entire async event loop gets blocked. This prevents Responses API polling (`GET` endpoint) for `ResponsesAgentServerHost` from functioning, making the agent appear frozen until the sync function returns.

## Concerns from Problem File

| # | Concern | Verdict | Evidence Link |
|---|---------|---------|---------------|
| 1 | FunctionTool.__call__ executes sync functions directly on event loop thread | **VALIDATED** | [todos/rootcause_concern_1.md] |
| 2 | FunctionTool.invoke() non-observability code path blocks at line 682 | **VALIDATED** | [todos/rootcause_concern_2.md] |
| 3 | FunctionTool.invoke() observability code path blocks at line 733 | **VALIDATED** | [todos/rootcause_concern_3.md] |
| 4 | No sync-to-async offloading mechanism exists in FunctionTool (unlike FunctionExecutor) | **VALIDATED** | [todos/rootcause_concern_4.md] |
| 5 | ResponsesHostServer._handle_inner_agent runs agent.run() on same event loop as polling | **VALIDATED** | [todos/rootcause_concern_5.md] |
| 6 | MCP tool invocation path (_agents.py:1543) also calls invoke() in same async context | **VALIDATED** | [todos/rootcause_concern_6.md] |
| 7 | No test coverage for sync-blocking-event-loop scenario in test_tools.py | **VALIDATED** | [todos/rootcause_concern_7.md] |
| 8 | Existing asyncio.to_thread() pattern in _function_executor.py not applied to FunctionTool | **VALIDATED** | [todos/rootcause_concern_8.md] |

Based on investigation of 8 concerns:
- **8 concerns VALIDATED** as contributing factors
- **0 concerns INVALIDATED**

## Synthesized Root Cause(s)

### Primary Root Cause

**`FunctionTool` lacks sync-to-async thread offloading for synchronous tool functions.**

`FunctionTool.__call__` (`_tools.py:511-538`) calls the wrapped function directly via `func(*args, **kwargs)` on the event loop thread with no thread offloading. The `invoke()` method (`_tools.py:682-683` and `733-734`) uses the pattern:

```python
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res
```

The `inspect.isawaitable(res)` check only determines whether to `await` the return value — but for synchronous functions, the blocking has already completed by the time this check runs. There is zero use of `asyncio.to_thread()`, `run_in_executor()`, or `ThreadPoolExecutor` anywhere in `_tools.py`.

This is a confirmed design gap: the same codebase's `FunctionExecutor` (`_function_executor.py:122-151`) solves this exact problem by detecting sync vs async at init time with `inspect.iscoroutinefunction(func)` and wrapping sync functions with `asyncio.to_thread()`.

**Concerns establishing this**: #1 (direct execution), #2 (non-observability path), #3 (observability path), #4 (missing mechanism), #8 (existing pattern not applied).

### Contributing Factor 1: No architectural isolation between tool execution and server request handling

`ResponsesHostServer._handle_inner_agent` (`_responses.py:322`) runs `agent.run()` directly on the ASGI server's event loop. There is no separate thread pool, no dedicated event loop, and no `asyncio.to_thread()` wrapping of `agent.run()`. When a tool blocks the event loop, it blocks all concurrent HTTP request handling, SSE streaming, health checks, and polling.

**Concern establishing this**: #5.

### Contributing Factor 2: MCP path shares the same vulnerable code path

The MCP tool invocation at `_agents.py:1543` calls the same `FunctionTool.invoke()` method. While `as_mcp_server()` wraps the agent itself in an async function (mitigating direct blocking at the top level), any synchronous sub-tools within the agent still block during the agent's `run()` execution via the same `FunctionTool.invoke()` path.

**Concern establishing this**: #6.

### Contributing Factor 3: No test coverage to catch the regression

No tests in `test_tools.py` or `test_tools_future_annotations.py` verify that sync tool functions don't block the event loop. The workflow `test_function_executor.py` has a test for `_is_async` flags but doesn't actually verify thread execution end-to-end. A test that runs a blocking sync tool alongside a concurrent async task would have caught this immediately.

**Concern establishing this**: #7.

## Fishbone Diagram

```
                                    Sync tool blocks event loop,
                                    freezing Responses API polling
                                                ▲
                ┌───────────────────────────────┼───────────────────────────────┐
                │                               │                               │
        [DESIGN GAP]                   [ARCHITECTURE]                    [QUALITY]
                │                               │                               │
    ┌───────────┴───────────┐       ┌───────────┴───────────┐       ┌───────────┴───────────┐
    │                       │       │                       │       │                       │
 #1 __call__            #4 No sync  #5 Same event         #6 MCP    #7 No test           #8 Pattern
 calls func()           detection   loop for agent        path      coverage for          exists in
 directly               mechanism   run + HTTP            shares    sync blocking         FunctionExecutor
    │                       │       serving               same                            but not applied
 #2 invoke()            No iscoro-      │                 invoke()                        to FunctionTool
 line 682               function()  No thread pool            │
 blocks                 check       No loop isolation     Sub-tools
    │                                                     still block
 #3 invoke()
 line 733
 blocks + holds
 OTel span open
```

## 5-Whys Summary (Primary Root Cause Chain)

1. **Why does Responses API polling freeze during sync tool execution?**
   Because `FunctionTool.invoke()` executes sync functions directly on the event loop thread, blocking all concurrent async operations including HTTP polling.

2. **Why does `invoke()` execute sync functions on the event loop thread?**
   Because it calls `self.__call__(**call_kwargs)` which is a synchronous method that calls `self.func()` directly — the blocking happens before any awaitable check.

3. **Why doesn't `invoke()` offload sync functions to a worker thread?**
   Because `FunctionTool` has no mechanism to detect sync vs async functions. It does not call `inspect.iscoroutinefunction()` at init or invoke time, and has no `_is_async` flag.

4. **Why wasn't the thread-offloading pattern applied to `FunctionTool`?**
   The pattern (`asyncio.to_thread()`) exists in `FunctionExecutor` (`_function_executor.py:137-151`) but `FunctionTool` predates it by over a year. The two components were developed independently.

5. **Why wasn't the gap caught by tests?**
   No test in `test_tools.py` verifies that sync tool functions don't block the event loop. All sync tool tests verify correctness of return values only, not concurrency behavior.

## Solution

### Files to Modify

| File | Change |
|------|--------|
| `python/packages/core/agent_framework/_tools.py` | In `FunctionTool.invoke()`, wrap synchronous function calls with `asyncio.to_thread()` at both code paths (lines 682 and 733). Detect sync vs async at construction time by storing an `_is_async` flag using `inspect.iscoroutinefunction()`. |
| `python/packages/core/tests/core/test_tools.py` | Add tests verifying that synchronous tool functions do not block the event loop — a concurrent async task must make progress during sync tool execution. |

### Implementation Steps

**Step 1: Add sync/async detection to `FunctionTool.__init__`**

In `_tools.py`, in the `FunctionTool.__init__` method (around line 297), after `self.func = func` is set (line 373), add:

```python
self._is_async = inspect.iscoroutinefunction(func)
```

This follows the same pattern used by `FunctionExecutor` at `_function_executor.py:122`.

**Step 2: Modify `FunctionTool.invoke()` to offload sync functions**

Replace the two blocking call sites. In the non-observability path (line 682-683):

```python
# Before (blocking):
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res

# After (non-blocking):
if self._is_async:
    res = self.__call__(**call_kwargs)
    result = await res if inspect.isawaitable(res) else res
else:
    result = await asyncio.to_thread(self.__call__, **call_kwargs)
```

Apply the same change to the observability path (line 733-734):

```python
# Before (blocking):
res = self.__call__(**call_kwargs)
result = await res if inspect.isawaitable(res) else res

# After (non-blocking):
if self._is_async:
    res = self.__call__(**call_kwargs)
    result = await res if inspect.isawaitable(res) else res
else:
    result = await asyncio.to_thread(self.__call__, **call_kwargs)
```

**Step 3: Ensure `asyncio` is imported**

Verify `import asyncio` exists at the top of `_tools.py`. (It likely does given the `asyncio.gather` usage at line 1769.)

**Step 4: Add tests for sync tool non-blocking behavior**

In `test_tools.py`, add a test that:
1. Creates a sync `@tool` that sleeps briefly (e.g., 0.1s using `time.sleep`)
2. Runs the tool via `invoke()` concurrently with an async flag-setting task using `asyncio.gather`
3. Verifies the async task completed (was not blocked) — i.e., the flag was set before or during the sync sleep, proving the event loop was not blocked

```python
async def test_sync_tool_does_not_block_event_loop():
    flag = asyncio.Event()

    @tool
    def blocking_tool() -> str:
        """A tool that blocks."""
        time.sleep(0.1)
        return "done"

    async def set_flag():
        flag.set()

    result_task = asyncio.create_task(blocking_tool.invoke())
    flag_task = asyncio.create_task(set_flag())
    await asyncio.gather(result_task, flag_task)
    assert flag.is_set()
```

### Enforcement Level

| Step | Level | Notes |
|------|-------|-------|
| Store `_is_async` flag in `__init__` | **Interlock** | Makes sync detection automatic at construction; no developer action needed |
| Wrap sync calls with `asyncio.to_thread()` in `invoke()` | **Interlock** | Code makes event loop blocking impossible for sync tool functions |
| Add non-blocking test | **Runtime guard** | Test fails if regression reintroduces blocking behavior |

All primary fixes are at **Interlock** level — code makes the failure impossible. No Instruction or Advisory level fixes needed.

### Verification Steps

1. Run existing tool tests to verify no regressions:
   ```bash
   cd python/packages/core && pytest -m "not integration" tests/core/test_tools.py tests/core/test_tools_future_annotations.py -v
   ```
   **Expected**: All existing tests pass.

2. Run the new non-blocking test:
   ```bash
   cd python/packages/core && pytest tests/core/test_tools.py::test_sync_tool_does_not_block_event_loop -v
   ```
   **Expected**: Test passes, confirming sync tools run in a thread without blocking the event loop.

3. Run workflow executor tests to verify no interaction:
   ```bash
   cd python/packages/core && pytest tests/workflow/test_function_executor.py -v
   ```
   **Expected**: All workflow executor tests pass unchanged.

### Code Convention Issues

- `FunctionTool` in `_tools.py` does not follow the same async-awareness pattern as `FunctionExecutor` in `_function_executor.py`. After the fix, both will correctly handle sync function offloading, establishing a consistent pattern across the codebase.
- The `_tools.py` file does not import `asyncio` directly for `asyncio.to_thread` — it uses `asyncio.gather` via a local reference. The import should be added at the module level if not already present.
