# Reproduction Report: Issue #4754

**Issue**: [Python: [Bug]: A2AAgent inconsistent with BaseAgent: context_providers not triggered](https://github.com/microsoft/agent-framework/issues/4754)
**Repository**: microsoft/agent-framework
**Investigated**: 2026-03-18 08:12:36 UTC
**Worktree Path**: `/repos/agent-framework/.worktrees/agent/fix-4754-1`
**Gate Result**: ✅ PASSED

---

## Reproduction Verdict

| Field | Value |
|-------|-------|
| Status | `reproduced` |
| Failure observed | `yes` |
| Evidence strength | `high` |
| Confidence | `high` |
| Failing test | `python/packages/a2a/tests/test_a2a_context_providers_bug.py` |
| Gate passed | ✅ PASSED |

## Finding

A2AAgent.run() completely bypasses context provider hooks. The word "context_provider" never appears in _agent.py. Two tests confirm that before_run and after_run are never called, reproducing the exact bug described in issue #4754.

## Files Examined

python/packages/a2a/agent_framework_a2a/_agent.py, python/packages/core/agent_framework/_agents.py, python/packages/core/agent_framework/_sessions.py, python/packages/a2a/tests/test_a2a_agent.py

## Tests Run

python/packages/a2a/tests/test_a2a_context_providers_bug.py::test_a2a_agent_context_providers_not_triggered, python/packages/a2a/tests/test_a2a_context_providers_bug.py::test_a2a_agent_context_providers_not_triggered_streaming, python/packages/a2a/tests/test_a2a_context_providers_bug.py::test_a2a_agent_accepts_context_providers_kwarg

## Full Analysis

No matches for `context_provider` in A2AAgent - confirming the issue. Let me check how BaseAgent handles context providers in its run flow.Now let me see the `run` method of `BaseAgent` and how it invokes context providers before/after:Now I have clear evidence. The `A2AAgent.run()` method (line 250) directly processes messages and returns without ever calling `_run_before_providers` or `_run_after_providers`. Let me now look at how another agent like `ChatCompletionAgent` handles this to confirm the pattern:Now let me look at the existing tests to understand test patterns and write a reproduction test:Now I have enough context. Let me write the reproduction test:Bug reproduced. 2 tests fail (context providers never called), 1 passes (providers are accepted but unused). Let me write the report.Bug confirmed with 2 failing tests. `A2AAgent.run()` bypasses the entire context provider lifecycle (`before_run`/`after_run`) that `BaseAgent` defines as a contract for all agents.

---

## Next Steps

- Reproduction confirmed — proceed to investigation and fix phase
- Review the failing test or evidence above to understand the root cause
- The issue branch is checked out in the worktree: `/repos/agent-framework/.worktrees/agent/fix-4754-1`