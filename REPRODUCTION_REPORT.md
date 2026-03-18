# Reproduction Report: Issue #4754

**Issue**: [Python: [Bug]: A2AAgent inconsistent with BaseAgent: context_providers not triggered](https://github.com/microsoft/agent-framework/issues/4754)
**Repository**: microsoft/agent-framework
**Investigated**: 2026-03-18 14:19:47 UTC
**Worktree Path**: `/repos/agent-framework/.worktrees/agent/fix-4754-2`
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

A2AAgent.run() (lines 250-302 in _agent.py) completely overrides BaseAgent.run() without ever calling _prepare_session_and_messages() or _run_after_providers(), which are the methods that invoke before_run/after_run on context_providers. A reproduction test confirms context_providers are silently ignored — the TrackingContextProvider's before_run_called remains False after agent.run() completes.

## Files Examined

python/packages/a2a/agent_framework_a2a/_agent.py, python/packages/core/agent_framework/_agents.py, python/packages/core/agent_framework/_sessions.py, python/packages/a2a/tests/test_a2a_agent.py

## Tests Run

python/packages/a2a/tests/test_a2a_context_providers_bug.py::test_a2a_agent_context_providers_triggered

## Full Analysis

Now let me look at how BaseAgent's `run` method handles context providers, specifically the `_prepare_session_and_messages` and the `_run_after_providers` calls:Now I have clear evidence. The A2AAgent's `run()` method (line 250-302) completely overrides BaseAgent's `run()` without calling `_prepare_session_and_messages()` (which runs `before_run` on providers) or `_run_after_providers()` (which runs `after_run`). Let me write a reproduction test.Now I have everything I need. Let me write and run the reproduction test:Bug reproduced. Now let me write the report:Bug confirmed. A2AAgent's `run()` overrides BaseAgent without calling any context provider hooks, so `before_run`/`after_run` on providers are never invoked.

---

## Next Steps

- Reproduction confirmed — proceed to investigation and fix phase
- Review the failing test or evidence above to understand the root cause
- The issue branch is checked out in the worktree: `/repos/agent-framework/.worktrees/agent/fix-4754-2`