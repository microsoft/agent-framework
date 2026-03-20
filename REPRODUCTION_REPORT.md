# Reproduction Report: Issue #4809

**Issue**: [Python: [Bug]: PydanticSchemaGenerationError in FunctionInvocationContext](https://github.com/microsoft/agent-framework/issues/4809)
**Repository**: microsoft/agent-framework
**Investigated**: 2026-03-20 22:54:50 UTC
**Worktree Path**: `/repos/agent-framework/.worktrees/agent/fix-4809-1`
**Gate Result**: ✅ PASSED

---

## Reproduction Verdict

| Field | Value |
|-------|-------|
| Status | `reproduced` |
| Failure observed | `yes` |
| Evidence strength | `high` |
| Confidence | `high` |
| Failing test | `/repos/agent-framework/.worktrees/agent/fix-4809-1/python/packages/core/tests/core/test_issue_4809_future_annotations.py` |
| Gate passed | ✅ PASSED |

## Finding

The exact FunctionInvocationContext filtering issue is fixed in current code (1.0.0rc5), but the root cause persists: _resolve_input_model uses raw param.annotation (string under PEP 563) instead of typing.get_type_hints(). This causes PydanticUserError when from __future__ import annotations is used with complex types like Optional[int]. The fix is to mirror _discover_injected_parameters' approach of calling typing.get_type_hints() in _resolve_input_model.

## Files Examined

python/packages/core/agent_framework/_tools.py, python/packages/core/tests/core/test_tools.py

## Tests Run

tests/core/test_issue_4809_future_annotations.py::test_tool_with_future_annotations_and_context_basic, tests/core/test_issue_4809_future_annotations.py::test_tool_with_future_annotations_optional_param, tests/core/test_issue_4809_future_annotations.py::test_tool_with_future_annotations_context_first, tests/core/test_issue_4809_future_annotations.py::test_tool_with_future_annotations_invoke

## Full Analysis

Now I have a clear picture. Let me check the `tool()` decorator and then write a reproduction test.Now I'll write the reproduction test. The bug manifests when `from __future__ import annotations` is used, causing `param.annotation` to be a string instead of a type.Both work. Let me try with custom types that would be harder for Pydantic to resolve from strings:Found a bug with `from __future__ import annotations`. Let me check `_annotation_includes_function_invocation_context` and test more scenarios:Now let me write the comprehensive reproduction test:One test fails. Now let me also test the exact scenario from the issue (without `from __future__ import annotations`) to check if that was already fixed:The exact scenario from the issue works in the current code (the `FunctionInvocationContext` filtering was likely added after the user's version). However, the underlying `_resolve_input_model` bug is still present with `from __future__ import annotations`. Let me verify the root cause in code:Confirmed: line 471 uses `param.annotation` directly (string under PEP 563) while `_discover_injected_parameters` at line 386 uses `typing.get_type_hints()`. Now let me write the report.**Results**: The exact issue from the reporter (on `1.0.0b17`) is fixed in the current `1.0.0rc5` codebase — `_discover_injected_parameters` now correctly filters `FunctionInvocationContext`. However, the **underlying bug persists**: `_resolve_input_model()` (line 471) uses raw `param.annotation` instead of `typing.get_type_hints()`, so `from __future__ import annotations` with complex types like `Optional[int]` still fails.

**Failing test**: `test_tool_with_future_annotations_optional_param` — `PydanticUserError: search_input is not fully defined; you should define Optional`.

---

## Next Steps

- Reproduction confirmed — proceed to investigation and fix phase
- Review the failing test or evidence above to understand the root cause
- The issue branch is checked out in the worktree: `/repos/agent-framework/.worktrees/agent/fix-4809-1`