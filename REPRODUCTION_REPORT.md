# Reproduction Report: Issue #5670

**Issue**: [Python: Remove Foundry toolbox helpers from FoundryChatClient; consume toolboxes via MCP](https://github.com/microsoft/agent-framework/issues/5670)
**Repository**: microsoft/agent-framework
**Investigated**: 2026-05-06 06:28:43 UTC
**Worktree Path**: `/repos/agent-framework/.worktrees/agent/fix-5670-1`
**Gate Result**: ✅ PASSED

---

## Reproduction Verdict

| Field | Value |
|-------|-------|
| Status | `feature_request` |
| Failure observed | `no` |
| Evidence strength | `high` |
| Confidence | `high` |
| Failing test | `none` |
| Gate passed | ✅ PASSED |

## Finding

This is a feature/enhancement request, not a bug. All symbols scheduled for removal (`fetch_toolbox`, `select_toolbox_tools`, `get_toolbox_tool_name`, `get_toolbox_tool_type`, `FoundryHostedToolType`, `ToolboxToolSelectionInput`, `RawFoundryChatClient.get_toolbox`, `ExperimentalFeature.TOOLBOXES`) are confirmed present in version 1.2.2. The unit-test suite passes cleanly, confirming the bespoke surface is functional and the requested removal has not yet occurred.

## Files Examined

python/packages/foundry/agent_framework_foundry/_tools.py, python/packages/foundry/agent_framework_foundry/_chat_client.py, python/packages/foundry/agent_framework_foundry/__init__.py, python/packages/core/agent_framework/foundry/__init__.py, python/packages/core/agent_framework/_feature_stage.py, python/packages/foundry/tests/test_toolbox.py

## Tests Run

python/packages/foundry/tests/test_toolbox.py (13 passed, 1 skipped — all unit tests pass against unmodified code)

## Full Analysis

All the evidence I need is gathered. Let me write the report.REPRODUCTION_SUMMARY:

---

## Next Steps

- Feature/enhancement request confirmed — proceed to investigation and implementation
- Use the evidence above to scope the missing capability instead of waiting for a failing repro
- The issue branch is checked out in the worktree: `/repos/agent-framework/.worktrees/agent/fix-5670-1`