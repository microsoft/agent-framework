# Reproduction Report: Issue #5112

**Issue**: [Python: [Bug]: Agent behaves differently with input when sent as string vs array - Difference is consistent](https://github.com/microsoft/agent-framework/issues/5112)
**Repository**: microsoft/agent-framework
**Investigated**: 2026-04-06 23:05:09 UTC
**Worktree Path**: `/repos/agent-framework/.worktrees/agent/fix-5112-1`
**Gate Result**: ✅ PASSED

---

## Reproduction Verdict

| Field | Value |
|-------|-------|
| Status | `reproduced` |
| Failure observed | `yes` |
| Evidence strength | `high` |
| Confidence | `high` |
| Failing test | `python/packages/devui/tests/devui/test_issue_5112_chat_completions_format.py` |
| Gate passed | ✅ PASSED |

## Finding

Bug reproduced with 2 failing tests. When input is sent as array in Chat Completions format (without "type": "message"), _convert_openai_input_to_chat_message silently skips the item at line 634, falling back to an empty text message at line 779. This causes the agent to receive no user query, explaining why it returns unfiltered tool results.

## Files Examined

python/packages/devui/agent_framework_devui/_executor.py, python/packages/devui/tests/devui/test_multimodal_workflow.py

## Tests Run

python/packages/devui/tests/devui/test_issue_5112_chat_completions_format.py

## Full Analysis

Now let me look at `_is_openai_multimodal_format` to understand the full path, and also check `_convert_input_to_chat_message`:Now I have clear evidence of the bug. Let me write a reproduction test.Bug is fully reproduced. Now let me write the report.Bug **confirmed and reproduced** with 2 failing tests. The root cause is in `_executor.py` line 634: `if item_type == "message"` only handles Responses API format, silently dropping Chat Completions format items (which lack `"type": "message"`), resulting in an empty user message.

---

## Next Steps

- Reproduction confirmed — proceed to investigation and fix phase
- Review the failing test or evidence above to understand the root cause
- The issue branch is checked out in the worktree: `/repos/agent-framework/.worktrees/agent/fix-5112-1`