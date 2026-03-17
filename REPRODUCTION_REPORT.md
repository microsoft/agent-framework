# Reproduction Report: Issue #4062

**Issue**: [Python: [Bug]: invoke_agent span reports last LLM call's token usage instead of aggregate total](https://github.com/microsoft/agent-framework/issues/4062)
**Repository**: microsoft/agent-framework
**Investigated**: 2026-03-17 11:48:54 UTC
**Worktree Path**: `/repos/agent-framework/.worktrees/agent/fix-4062-1`
**Gate Result**: ✅ PASSED

---

## Reproduction Verdict

| Field | Value |
|-------|-------|
| Status | `reproduced` |
| Failure observed | `yes` |
| Evidence strength | `high` |
| Confidence | `high` |
| Failing test | `python/packages/core/tests/core/test_issue_4062_token_aggregation.py` |
| Gate passed | ✅ PASSED |

## Finding

Bug reproduced with a failing test. The FunctionInvocationLayer._get_response() loop in _tools.py returns only the last ChatResponse without aggregating usage_details across iterations. The invoke_agent span reports input_tokens=2569 (last call) instead of the expected 4808 (sum of all calls). The add_usage_details() helper exists but is not used in the loop.

## Files Examined

python/packages/core/agent_framework/_tools.py, python/packages/core/agent_framework/observability.py, python/packages/core/agent_framework/_agents.py, python/packages/core/agent_framework/_types.py, python/packages/core/tests/core/conftest.py, python/packages/core/tests/core/test_observability.py

## Tests Run

python/packages/core/tests/core/test_issue_4062_token_aggregation.py::test_invoke_agent_span_aggregates_token_usage

## Full Analysis

Now I see the issue. The `_get_response_attributes` at line 1911 reads `response.usage_details` directly from the AgentResponse, and the `invoke_agent` span at line 1628 just uses whatever is in the response. Let me check what `AgentResponse.usage_details` contains.Now let me find where the agent loop runs and how it sets `usage_details` on the `AgentResponse`.Now let me find the `get_response` method on the chat client to see how it handles the agent loop with tool calls and token aggregation.The OpenAI chat client just parses a single response. The agent loop with tool calls must happen in the `_clients.py` or somewhere that handles function execution. Let me look at the function handler / auto-invocation.Good, let me look at the core agent loop. The `WorkflowAgent` aggregates usage. But for a regular `RawAgent`, the `get_response` is what matters. Let me look at the function-calling loop.I can now see the bug. The `FunctionInvocationLayer._get_response()` loop (lines 2154-2268) runs multiple `super_get_response` calls but only returns the last `response` — never aggregating `usage_details` across iterations.

Let me check existing tests and write a reproduction test.Now let me look at the existing test patterns for agent telemetry and understand the test infrastructure.Now let me look at the conftest and test setup for span_exporter fixture:Now I have all the information needed. Let me look at the `span_exporter` fixture:Now I have everything I need. Let me write the reproduction test.Need to fix the `Content.from_function_call` API. Let me check the correct signature:The function invocation loop isn't running. Let me check how the existing tests set up tool calling correctly:Now I see the pattern. I should use `MockBaseChatClient` from conftest and pre-load `run_responses` with usage details. Let me rewrite the test properly:The `options` is being passed in `client_kwargs` but the agent already sends options. Let me fix the approach — pass tools directly to the agent:I see — the agent has `tools` parameter and `options` parameter. Let me just pass tools via options dict:The bug is confirmed. The test fails exactly as described in issue #4062: the `invoke_agent` span reports `input_tokens=2569` (last call only) instead of `4808` (aggregate).

Now let me write the reproduction report.REPRODUCTION_SUMMARY:

---

## Next Steps

- Reproduction confirmed — proceed to investigation and fix phase
- Review the failing test or evidence above to understand the root cause
- The issue branch is checked out in the worktree: `/repos/agent-framework/.worktrees/agent/fix-4062-1`