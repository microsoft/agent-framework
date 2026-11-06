# Tool Approval Budget State Cleanup on Turn Failure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure `ToolApprovalMiddleware` per-attempt function-invocation budget state in `session.state` is cleaned up after provider errors, timeouts, and cancellations, preventing budget exhaustion on retry turns while preserving resumable pending approvals.

**Architecture:** In `_tools.py`, integrate `_clear_budget_state_from_session` into exception, task cancellation, and generator exit paths of the tool execution loop. The cleanup will check `invocation_session.state[_TOOL_APPROVAL_STATE_KEY]`: if active approval requests or pending pause batches are waiting for human resolution, the budget is preserved; otherwise, stale per-turn iteration and duration counts are purged.

**Tech Stack:** Python 3.10+, `pytest`, `pytest-asyncio`, `agent_framework`.

**Spec:** GitHub Issue #9677 (https://github.com/microsoft/agent-framework/issues/9677), triage planning directive by maintainer `eavanvalkenburg`.

## Global Constraints

- Never clear budget state when a run pauses for human-in-the-loop approval (`_PENDING_APPROVAL_REQUESTS_KEY` or `_PENDING_MIXED_PAUSE_BATCH_KEY`).
- Maintain exact streaming and non-streaming parity.
- Must not touch public agent APIs, middleware interfaces, or `AgentSession` contracts.
- Tests must use mocked LLM chat clients without cloud credentials or network access.

## Review Focus

- Turn retries immediately following a transient provider exception.
- Turn retries following an `asyncio.CancelledError` or client timeout.
- Preservation of pending approval requests across session serialization.
- Streaming generator early-break / generator close cleanup.
- Preservation of legitimate cross-turn multi-agent memory in `session.state`.

---

### Task 1: Add Reproducing Regression Tests for Issue #9677

**Files:**
- Modify/Create: `python/packages/core/tests/core/test_tool_approval_budget.py`

**Interfaces:**
- Consumes: `Agent`, `AgentSession`, `ToolApprovalMiddleware`, mock chat client.
- Produces: Test functions validating budget clearance on failure and budget retention on approval pause.

- [ ] **Step 1: Write reproducing unit tests**

```python
import pytest
from agent_framework import Agent, AgentSession, Message
from agent_framework._harness._tool_approval import ToolApprovalMiddleware
from agent_framework._tools import _FUNCTION_INVOCATION_BUDGET_STATE_KEY


@pytest.mark.asyncio
async def test_failed_turn_clears_budget_state_on_session(mock_failing_chat_client) -> None:
    session = AgentSession()
    agent = Agent(
        client=mock_failing_chat_client,
        middleware=[ToolApprovalMiddleware()],
    )

    with pytest.raises(RuntimeError, match="transient provider error"):
        await agent.run("call tool", session=session)

    # Budget key must be cleared from session after failure
    assert _FUNCTION_INVOCATION_BUDGET_STATE_KEY not in session.state
```

- [ ] **Step 2: Run test to verify failure on current main**

Run: `uv run pytest packages/core/tests/core/test_tool_approval_budget.py`
Expected: FAIL with `assert '_function_invocation_budget_state' not in session.state` failing.

---

### Task 2: Implement Unwinding Budget Cleanup in `_tools.py`

**Files:**
- Modify: `python/packages/core/agent_framework/_tools.py`

**Interfaces:**
- Consumes: `_clear_budget_state_from_session(invocation_session, budget_state)`
- Produces: Hardened error and cancellation handlers in runtime invocation loops.

- [ ] **Step 1: Update non-streaming tool invocation loop error handling**

Ensure that on any caught unhandled exception, task cancellation, or abnormal loop termination, `_clear_budget_state_from_session(invocation_session, budget_state)` is invoked in a `finally` or exception boundary.

- [ ] **Step 2: Update streaming generator termination handlers**

Ensure that streaming generator cancellation and generator `aclose()` trigger the same `_clear_budget_state_from_session` check.

- [ ] **Step 3: Run regression tests to verify pass**

Run: `uv run pytest packages/core/tests/core/test_tool_approval_budget.py`
Expected: PASS.

- [ ] **Step 4: Run full core test suite**

Run: `uv run pytest packages/core/tests/core/test_tools.py`
Expected: All tests pass.
