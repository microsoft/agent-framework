reproduction_status: reproduced
failing_test: packages/core/tests/core/test_issue_1366_thread_corruption.py::test_max_iterations_exhausted_makes_final_toolchoice_none_call AND packages/core/tests/core/test_issue_1366_thread_corruption.py::test_max_iterations_preserves_all_fcc_messages
failure_observed: yes
evidence_strength: high
confidence: high

# Issue #1366 Reproduction: Thread corruption - agent.run() returns with unexecuted tool calls

## Bug Summary

When the function invocation loop in `_tools.py` exhausts `max_iterations`, it returns the response directly without:
1. Making a final model call with `tool_choice="none"` (failsafe)
2. Prepending `fcc_messages` from prior iterations to the response

## Code Location

**File**: `python/packages/core/agent_framework/_tools.py`

**Bug location** (lines 2199-2200 in `_get_response()`):
```python
if response is not None:
    return response  # Returns directly, bypasses failsafe at lines 2202-2212
```

The failsafe path (lines 2202-2212) that calls the model with `tool_choice="none"` and prepends `fcc_messages` is ONLY reached when `response is None` (i.e., the loop never ran). When `max_iterations > 0`, the loop always runs at least once, setting `response` to a non-None value. Therefore, the failsafe path is **dead code** for any normal configuration.

**Streaming equivalent** (line 2336-2337 in `_stream()`):
```python
if response is not None:
    return  # Same issue in streaming path
```

## Failing Tests

### Test 1: `test_max_iterations_exhausted_makes_final_toolchoice_none_call` — FAILED
```
AssertionError: Expected failsafe text response, got: ''
assert '' == 'I broke out of the function invocation loop...'
```
**Demonstrates**: When max_iterations is reached with the model still requesting tools, no final `tool_choice="none"` call is made. The response ends with function_call/result messages instead of a clean text response.

### Test 2: `test_max_iterations_preserves_all_fcc_messages` — FAILED
```
AssertionError: First iteration's function call missing from response
assert 'call_1' in {'call_2'}
```
**Demonstrates**: Only the LAST iteration's function call/result messages are in the response. Prior iterations' messages (accumulated in `fcc_messages`) are discarded because `_prepend_fcc_messages()` is never called on this code path.

### Test 3: `test_max_iterations_exhausted_returns_orphaned_function_calls` — PASSED
Within a single response, function calls within each iteration ARE matched with results.

### Test 4: `test_thread_safe_after_max_iterations_with_agent` — PASSED
At the Agent level, function calls in the returned response have matching results.

## Pre-existing Evidence

The existing test `test_max_iterations_limit` (line 836) is **explicitly skipped** with:
```python
@pytest.mark.skip(reason="Failsafe behavior with max_iterations needs investigation in unified API")
```
This confirms the development team is aware the failsafe behavior is broken.

## How This Causes the Reported 400 Error

While individual function calls within each iteration are matched (tests 3-4 pass), the thread corruption manifests in two ways:

1. **Lost conversation history**: When the response only contains the last iteration's messages, the thread stored by `InMemoryHistoryProvider.after_run()` (via `context.response.messages`) is incomplete. Prior iterations' function calls and results are discarded.

2. **No final text response**: Without the failsafe `tool_choice="none"` call, the response ends with a tool message (function results). The model is never asked to produce a final answer. Depending on how the caller manages the thread, this incomplete state can lead to the OpenAI 400 error on the next API call when the conversation context doesn't match what the model expects.

## Fix Direction (DO NOT implement in this phase)

The fix should ensure that when `max_iterations` is exhausted:
1. A final model call is made with `tool_choice="none"` to get a clean text response
2. All `fcc_messages` from prior iterations are prepended to the response
3. OR: inject error `FunctionResultContent` for any orphaned `FunctionCallContent` as the issue suggests

## Run Command

```bash
cd python && uv run pytest packages/core/tests/core/test_issue_1366_thread_corruption.py -v
```
