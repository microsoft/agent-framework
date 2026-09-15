# Bug Hunt Report — microsoft/agent-framework (Python)

- **Base**: `main` @ `1cd06c5a2` (2026-09-13), working only in `python/`
- **Method**: pristine repro → not-intended check (tests + git log) → un-reported check (open+closed issue search) → fix + regression tests that fail on pristine → branch per fix (no push, no filings)
- **Result**: **2 solid bugs found, fixed, and verified**

| # | Bug | Root cause | Branch |
|---|-----|-----------|--------|
| A | `Literal` message annotations crash every workflow at delivery time with `TypeError: typing.Literal cannot be used with isinstance()` | `agent_framework/_workflows/_typing_utils.py:158` (`is_instance_of`) | `fix/is-instance-of-literal` |
| B | `prepend_instructions_to_messages()` inverts instruction order when only a prefix of instructions is deduplicated | `agent_framework/_types.py:1981` | `fix/prepend-instructions-order` |

All paths below are relative to `python/packages/core/`.

---

## Bug A — Literal handler annotations crash at runtime (`is_instance_of`)

**Branch**: `fix/is-instance-of-literal` (1 commit, author: Manohar Paturi)

### Repro (fails on pristine `main`)

```python
import asyncio
from typing import Literal
from typing_extensions import Never
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

class LiteralExecutor(Executor):
    @handler
    async def handle(self, message: Literal["yes", "no"], ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(f"got:{message}")

wf = WorkflowBuilder(start_executor=LiteralExecutor(id="lit")).build()
print(asyncio.run(wf.run("yes")).get_outputs())
# pristine: TypeError: typing.Literal cannot be used with isinstance()
```

### Root cause

`agent_framework/_workflows/_typing_utils.py:158` — `is_instance_of()` has cases for `Any`, non-generics, `Union`/`|`, `list`/`set`, `tuple`, `dict`, and other generic origins, but **no case for `Literal`**. For `Literal["yes", "no"]`, `get_origin(...)` is `Literal`, so control reaches `isinstance(data, Literal)` (directly, or via the Case-6 origin check), which always raises `TypeError`.

`Executor.can_handle()` (`_executor.py:383`) and `Executor._find_handler()` call `is_instance_of()` directly on every message delivery, so the crash is unavoidable at runtime — even though:

- `@handler` registration accepts a `Literal` message annotation (only unresolved `TypeVar`s are rejected),
- `WorkflowBuilder` type-compatibility validation accepts it (`is_type_compatible` compares equal `Literal`s as equal),
- the sibling helper `_matches_annotation()` **in the same module family** already implements the correct `Literal` matching semantics for `try_coerce_to_type` — i.e. the framework elsewhere supports `Literal` annotations and this path was simply missed.

So a definition that passes every static gate dies on the first delivered message — the worst failure mode.

### Fix

Added a `Literal` case to `is_instance_of()` that matches by allowed values with strict member types (`bool` never matches an `int` member), mirroring `_matches_annotation`:

```python
# Case 1b: target_type is Literal[...]
if origin is Literal:
    return any(data == member and type(data) is type(member) for member in args)
```

### Evidence

- **Fail-on-pristine**: `tests/workflow/test_typing_utils.py::test_literal_types`, `tests/workflow/test_executor.py::test_executor_literal_message_annotation`, `tests/workflow/test_executor.py::test_workflow_with_literal_message_annotation` → `3 failed` on pristine source (fix stashed); `3 passed` with the fix.
- **No regressions**: `tests/workflow/` → `1015 passed, 2 skipped, 2 xfailed`; `tests/core/` → `3778 passed, 132 skipped` (a post-session OTel console-exporter `ValueError` during interpreter teardown reproduces identically on pristine and is unrelated).
- **Not intended**: no test pins the crash (the only `Literal` test, `test_coerce_dict_to_dataclass_checks_literal_fields`, exercises `_matches_annotation`, which works around `is_instance_of`); docs of `is_instance_of` make no exception for `Literal`.
- **Un-reported**: issue search `Literal handler`, `Literal isinstance`, `Literal executor workflow` → nothing matching (nearest: #7222, unrelated tool-arg validation).

### Draft issue body

> **Title**: Python: [Bug]: Executors with `Literal` message annotations crash at delivery with `TypeError: typing.Literal cannot be used with isinstance()`
>
> **Description**: A workflow executor handler annotated with a `Literal` message type passes `@handler` registration, executor construction, and `WorkflowBuilder` type validation, but the workflow crashes the first time a message is delivered to it:
>
> ```python
> from typing import Literal
> from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
>
> class ChoiceExecutor(Executor):
>     @handler
>     async def handle(self, message: Literal["yes", "no"], ctx: WorkflowContext) -> None: ...
>
> wf = WorkflowBuilder(start_executor=ChoiceExecutor(id="choice")).build()
> await wf.run("yes")
> ```
>
> ```text
> TypeError: typing.Literal cannot be used with isinstance()
> ```
>
> **Root cause**: `is_instance_of()` in `agent_framework/_workflows/_typing_utils.py` has no `Literal` case and falls through to `isinstance(data, Literal)`. `Executor.can_handle()` / `Executor._find_handler()` call it directly on every delivery. `_matches_annotation()` in the same module already implements the intended `Literal` semantics (value equality with strict member types) — `is_instance_of` just lacks the case.
>
> **Expected**: delivery-time matching should accept values equal to a `Literal` member (with the member's exact type, so `True` does not match `Literal[1]`) and reject others, consistent with `_matches_annotation`.
>
> **Proposed fix**: add `if origin is Literal: return any(data == member and type(data) is type(member) for member in args)` to `is_instance_of`.

---

## Bug B — partial instruction dedup inverts instruction order

**Branch**: `fix/prepend-instructions-order` (1 commit, author: Manohar Paturi)

### Repro (fails on pristine `main`)

```python
from agent_framework import Message, prepend_instructions_to_messages

messages = [
    Message("system", ["First instruction"]),
    Message("user", ["Hello"]),
]
result = prepend_instructions_to_messages(messages, ["First instruction", "Second instruction"])
print([m.text for m in result])
# pristine: ['Second instruction', 'First instruction', 'Hello']   <-- order inverted
# expected: ['First instruction', 'Second instruction', 'Hello']
```

### Root cause

`agent_framework/_types.py:1981` (`prepend_instructions_to_messages`). The dedup introduced in #5051 (external PR fixing #5049) collects every instruction not matched positionally and **prepends the remainder in front of all messages** — including in front of the already-present matched instructions:

```python
deduplicated: list[str] = []
for idx, instr in enumerate(instructions):
    if idx < len(messages) and messages[idx].role == role and messages[idx].text == instr:
        continue
    deduplicated.append(instr)
...
instruction_messages = [Message(role, [instr]) for instr in deduplicated]
return [*instruction_messages, *messages]
```

For instructions `["First", "Second"]` where `"First"` is already the leading system message, the remainder `["Second"]` is placed *before* the existing `"First"` message, silently reversing the requested instruction order. System-prompt order is semantically meaningful (e.g. layered agent + client instructions merged by `_merge_options`/`_append_instructions`, which preserve order as a list). All existing tests cover only the full-prefix or no-match cases, so the partial case regresses unnoticed.

### Fix

Deduplicate only the **matching prefix** and insert the remaining instructions immediately after it:

```python
matched_count = 0
for idx, instr in enumerate(instructions):
    if idx < len(messages) and messages[idx].role == role and messages[idx].text == instr:
        matched_count += 1
    else:
        break
if matched_count == len(instructions):
    return messages
instruction_messages = [Message(role, [instr]) for instr in instructions[matched_count:]]
return [*messages[:matched_count], *instruction_messages, *messages[matched_count:]]
```

This also makes the dedup contiguous-prefix (a leading mismatch stops matching), which is strictly more conservative than the old positional matching. All previously tested behaviors (no match → plain prepend; full match → unchanged; single instruction) are byte-for-byte identical.

### Evidence

- **Fail-on-pristine**: `tests/core/test_types.py::test_prepend_instructions_partial_dedup_preserves_order` → `1 failed` on pristine source; `8 passed` (all prepend tests incl. new ones) with the fix.
- **No regressions**: `tests/core/` full suite → `3780 passed, 132 skipped`.
- **Not intended**: the introducing commit 7e8e9e307 (#5051) states the goal as "skip instructions that are already present as leading messages" — silent reordering of the remaining instructions is not part of the intent; no test pins the reorder.
- **Un-reported**: issue search `prepend_instructions` / instructions order → nothing (nearest hits #8122, #6794 are unrelated Claude fixes).

### Draft issue body

> **Title**: Python: [Bug]: `prepend_instructions_to_messages()` inverts instruction order when only a prefix is deduplicated
>
> **Description**: When some (but not all) instructions are already present as leading messages, the remaining instructions are prepended *in front of* the already-present ones, reversing their relative order:
>
> ```python
> from agent_framework import Message, prepend_instructions_to_messages
>
> messages = [Message("system", ["First"]), Message("user", ["Hello"])]
> result = prepend_instructions_to_messages(messages, ["First", "Second"])
> print([m.text for m in result])
> # ['Second', 'First', 'Hello']  — expected ['First', 'Second', 'Hello']
> ```
>
> This matters when instruction lists are built by merging agent and chat-client instructions (order is preserved as a list by `_merge_options`); a partial dedup silently reorders the system prompt.
>
> **Root cause**: `_types.py`, `prepend_instructions_to_messages` — the non-matching remainder is collected and prepended before all messages, including before the matched leading instructions.
>
> **Proposed fix**: deduplicate only the matching *prefix* of instructions and insert the remainder immediately after it.

---

## Investigated and discarded (with reasons)

1. **`SerializationMixin.to_dict()` silently drops `datetime`/`date`/`time` outside dict values** (`_serialization.py::_serialize_value`; e.g. `ChatResponse(created_at=datetime(...)).to_json()` loses `created_at`, and `additional_properties={"days": [date, date]}` serializes to `{"days": []}`). Real and nasty, **but** `test_to_dict_only_converts_date_time_in_dict_values` (added in #7790) explicitly pins this exact behavior as a characterization test → fails the "not intended" bar. Candidate for a behavior-change proposal instead of a bug filing.
2. **`@response_handler` breaks with `from __future__ import annotations`** (string annotations never resolved in `_validate_response_handler_signature`; either a baffling class-creation error or silent string-keyed handler registration that never matches at runtime). Real, **but** already reported as open issue **#8327** (same root cause/file/fix).
3. **`WorkflowExecutor._handle_response` drops `tools=`/kwargs on response resume** — already reported as **#8344**.
4. Checkpoint storage/encoding family (concurrent saves, base64 validation, dict-key collisions) — already covered by open issues **#8181, #8182, #8255, #8256, #8257, #7831**.
5. Verified-clean during the hunt (no bugs found despite targeted differential testing): in-memory vector store scoring/filter/threshold/paging (`_in_memory.py`), `Content`/`Message` dict round-trips, `State` pending/commit semantics, fan-in/fan-out/switch-case edge routing and buffer snapshots, `add_usage_details`, `merge_chat_options`, `is_type_compatible`, workflow cancellation + re-run guard.

## Verification environment

- Python 3.14.7, macOS arm64; editable install of `python/packages/core[dev]` from the clone
- pytest 9.1.1, pytest-asyncio 1.4.0 (asyncio_mode=auto)
- Branches (local only, not pushed): `fix/is-instance-of-literal` (8d310f584), `fix/prepend-instructions-order` (43b4504e0), both off `main` (1cd06c5a2)
