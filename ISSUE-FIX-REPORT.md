# Issue #1366 Fix Report: Thread corruption - agent.run() returns with unexecuted tool calls

## Pattern Exploration (3+ references)

### 1. Error threshold pattern (`_tools.py:2163-2166`)
When consecutive errors reach `max_consecutive_errors_per_request`, the code sets `tool_choice="none"` and **continues the loop**. The next iteration calls the model without tools, producing a clean text response. The `_process_function_requests` function detects no function calls and returns `action="return"`, which prepends `fcc_messages` via `_prepend_fcc_messages()` (line 1974).

### 2. max_function_calls pattern (`_tools.py:2167-2179`)
When `total_function_calls >= max_function_calls`, identical to the error pattern: sets `tool_choice="none"` and continues. The next iteration gets a toolless response and exits cleanly with history attached.

### 3. Normal exit pattern (`_tools.py:2160-2161, 1971-1982`)
When the model's response has no function calls, `_extract_function_calls()` returns empty, triggering `_prepend_fcc_messages(response, fcc_messages)` before returning. This ensures all accumulated conversation history from prior iterations is included.

### Chosen approach
All three patterns converge on the same mechanism: when stopping tool calls, make a final model call with `tool_choice="none"` and use `_prepend_fcc_messages` to attach history. The fix follows this exact pattern for `max_iterations` exhaustion.

## Root Cause

**File**: `python/packages/core/agent_framework/_tools.py`, lines 2199-2200 (non-streaming) and 2336-2337 (streaming).

When the for-loop exhausts `max_iterations`, the code did:
```python
if response is not None:
    return response  # Premature return — bypasses failsafe
```

Since the loop always sets `response` to a non-None value (any `max_iterations >= 1`), the failsafe code (lines 2202-2212) that calls the model with `tool_choice="none"` and prepends `fcc_messages` was **unreachable dead code**.

This caused two problems:
1. **No final text response**: The model was never asked to produce a text answer after tool execution stopped
2. **Lost conversation history**: `fcc_messages` accumulated from prior iterations was never prepended to the response

## Code Changes

### `python/packages/core/agent_framework/_tools.py`
**Non-streaming** (line 2199): Changed `if response is not None: return response` to a log statement, allowing the existing failsafe code to execute.
**Streaming** (line 2343): Same change for the streaming path.

Both paths now:
1. Log that max_iterations was reached (matching the `max_function_calls` log pattern)
2. Fall through to the failsafe: call model with `tool_choice="none"` and prepend `fcc_messages`

### `python/packages/core/tests/core/test_function_invocation_logic.py`
Removed `@pytest.mark.skip` from `test_max_iterations_limit` (2 duplicate skip markers) and `test_streaming_max_iterations_limit` (1 skip marker). These tests validate the exact behavior that is now fixed.

### `python/packages/core/tests/core/test_issue_1366_thread_corruption.py` (new)
4 targeted tests covering:
- Orphaned FunctionCallContent detection
- Final `tool_choice="none"` failsafe call
- `fcc_messages` preservation across iterations
- Full Agent.run() → thread integrity

## Test Evidence

### Before fix
```
test_max_iterations_exhausted_makes_final_toolchoice_none_call  FAILED
  AssertionError: Expected failsafe text response, got: ''
test_max_iterations_preserves_all_fcc_messages                  FAILED
  AssertionError: First iteration's function call missing from response
test_max_iterations_limit                                       SKIPPED
test_streaming_max_iterations_limit                             SKIPPED
```

### After fix
```
packages/core/tests/core/test_issue_1366_thread_corruption.py   4 passed
packages/core/tests/core/test_function_invocation_logic.py      80 passed, 2 skipped
packages/core/tests/core/ (full suite)                          878 passed, 18 skipped
```

## Remaining Risks

1. **Extra model call**: The fix adds one additional API call when `max_iterations` is exhausted. This is intentional — the error/max_function_calls paths already do this — but could increase latency/cost in edge cases.

2. **Conversation-based APIs**: For APIs where `conversation_id` is set, `prepped_messages` is cleared and only the last message is kept (line 2192-2194). The failsafe call sends this minimal context, which should be correct since the server retains full history, but this path is not covered by unit tests.

3. **Streaming `fcc_messages`**: The streaming failsafe doesn't explicitly prepend `fcc_messages` (it doesn't need to — prior iterations' updates were already yielded). However, the finalized `ChatResponse.from_updates()` aggregates all yielded updates, which should produce a complete response.
