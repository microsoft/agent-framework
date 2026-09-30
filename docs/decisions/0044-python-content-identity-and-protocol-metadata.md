---
status: proposed
contact: eavanvalkenburg
date: 2026-09-30
deciders: eavanvalkenburg
consulted:
informed:
---

# Separate identity and protocol metadata in Python content

## Context and Problem Statement

Python `Content` and `Message` have first-class identity fields (`Content.id`, `call_id`, `status`,
`protected_data`, `name`, `file_id`, `server_name`, `Message.message_id`) and an open `additional_properties`
mapping. `to_dict()` persists `additional_properties` but drops `raw_representation`, so anything a provider or host
needs to replay persisted history must live in fields or `additional_properties`.

There is no rule for which data goes where. On current `main`, providers and hosts have independently introduced
more than 25 metadata keys, and several cross package boundaries:

| Problem | Examples on `main` |
| --- | --- |
| Provider item IDs have no fixed location | OpenAI Responses stores a function call's item ID in `fc_id`, hosted custom/tool-search items in `item_id`, and reasoning and computer-call item IDs in `Content.id`. Hosting Responses reads `fc_id` and emits it as its own output item ID. |
| Core behavior depends on provider keys | Core treats a function call as hosted whenever `additional_properties["server_label"]` is truthy. That one check controls approval handling, session resumption, skills and file-access auto-approval rules, and continuation error results. The same key is also persisted as the hosted server boundary in harness always-approve rules. Core streaming aggregation falls back to `additional_properties["item_id"]` to correlate code-interpreter fragments. |
| One concept, inconsistent representations | Function-call `status` is stored as metadata although `Content.status` exists. File names are stored as `filename` although `Content.name` exists. A hosted MCP server's name is `server_name` on MCP call content but `server_label` metadata on the call nested in a hosted approval. |
| Inconsistent key naming | `openai.responses.shell.output_type`, `openai.local_shell_command_parts`, `__foundry_reasoning_replay_item__`, `openai_content_type`, `computer_action_format`, and AG-UI's underscore-prefixed `_agui_collected_approval_occurrence`. |
| Replay depends on non-persisted objects | OpenAI shell replay, Gemini tool-call parts, Hosting Responses output reuse, and a Foundry hosting OAuth fallback read `raw_representation`, which is absent after history is reloaded. |

Each new provider feature adds another key, and consolidating the duplicated Responses conversions is not possible
while every adapter decides placement independently.

[Spec 004](../specs/004-python-function-calling-loop.md) already defines function-call identity:
`function_call.Content.id` identifies one locally actionable Agent Framework occurrence, while `call_id` is the
provider's call/result correlation. [ADR 0039](0039-python-refusal-content.md) defines the flat
`model_output_kind="refusal"` marker. This decision builds on both and changes neither.

`additional_properties` merges are shallow and not uniform: text, reasoning, and function-call addition keeps the
existing value on collision, code-interpreter aggregation keeps the incoming value, and nested values are shared by
copies. Any convention must remain correct under those rules.

## Decision Drivers

- Keep function-call occurrence identity unambiguous and separate from provider identifiers.
- Replay persisted history without `raw_representation`.
- Base core behavior, especially approval handling, on documented first-class fields rather than provider keys.
- Keep existing histories and pending approvals readable after upgrading.
- Keep independently versioned packages working together in one process.
- Keep core provider-neutral and avoid growing `Content` for provider-specific concepts.
- Behave predictably under shallow merges and copies.
- Give contributors a rule that is simple to follow and to test.

## Considered Options

1. Document the current keys without changing them.
2. Add first-class provider identity fields, such as `provider_item_id`, to `Content`.
3. Store each protocol's metadata in one nested mapping, such as `additional_properties["openai.responses"]`.
4. Use existing first-class fields, flat namespaced keys for provider data, and a small set of reserved flat keys.

## Decision Outcome

Chosen option: **"Use existing first-class fields, flat namespaced keys for provider data, and a small set of reserved
flat keys"**. It fixes the ambiguous and cross-package cases without adding provider concepts to core, and it is the
only option that works unchanged with the existing merge behavior.

### Identity

- `function_call.Content.id` is only the Agent Framework occurrence identity defined by spec 004. Adapters never
  write a provider identifier to it.
- `call_id` is the correlation between a call and its result. When a hosted protocol item exposes only one
  identifier and Agent Framework needs to pair call and result contents, adapters use that identifier as `call_id`.
  This replaces core's code-interpreter fallback on `item_id`.
- A provider item ID that has no first-class field is stored under the provider's namespace, for example
  `openai.responses.item_id` for function calls and function results.
- Existing uses of `Content.id` for a provider identifier remain documented exceptions: reasoning items, computer
  calls and results, and hosted-tool approval requests, which keep the provider's approval ID. Local approval
  requests use the occurrence ID, as spec 004 defines. New content types do not extend the exceptions without a
  decision.
- A host owns the identifiers it emits. It must not substitute one kind of identifier for another, such as a
  `call_id` or occurrence ID as an output item ID. It reads upstream item IDs only from their documented location.

### Hosted tool calls

`function_call` content gets an explicit first-class `hosted` field. `True` means the provider or service executes
the call and Agent Framework must never execute it locally; `False` means a local call. Every current use of
`server_label` as a hosted marker switches to this field: in core's approval handling, session resumption, skills
and file-access auto-approval rules, and continuation error results, and in AG-UI, Foundry hosting, and Hosting
Responses.

The hosted server's identity moves to the existing `server_name` field, which harness always-approve rules use as
the server boundary. Because routing no longer depends on it, `server_name` remains descriptive. Hosted approval
requests and responses continue to nest a `function_call`, so serializers keep their current shape.

Adapters set `hosted=True` on every call the provider executes, including the call nested in a hosted approval
request. A provider-issued approval left unmarked would be treated as a local call, so every adapter that parses
provider approvals must test that it sets the field. The field records who executes the call; it does not establish
trust. Trust still comes from where the content originated: spec 004's trusted pending snapshot for local approvals,
and the provider for hosted ones.

Two alternatives were rejected. Nesting `mcp_server_tool_call` in hosted approvals would still infer routing from
content type, and would change every approval serializer. Setting `server_name` on the nested call would turn a
descriptive field into a routing signal that a local tool adapter could reasonably set later.

#### Legacy records and older producers

- `Content.to_dict()` always writes `hosted` for `function_call` content, as `true` or `false`. A record that contains
  `hosted` is a new record: its value must be a boolean, anything else is rejected, and it always takes precedence
  over `server_label`.
- When `hosted` is not supplied, the constructor infers it: `True` if `additional_properties["server_label"]` is set,
  otherwise `False`. Inferring `True` emits a `FutureWarning` identifying the legacy `server_label` form. This covers
  records written before this change and older provider packages that construct content on a newer core.
- `Content.from_dict()` builds content through the constructor, so the same inference applies to messages,
  responses, sessions, history providers, harness approval state, and calls nested in approval requests.
- Workflow checkpoints pickle `Content` and restore it through `__setstate__`, which bypasses `from_dict()`.
  `__setstate__` applies the same inference and warning.
- Hosts, AG-UI, and DevUI build content from their own wire formats; they set `hosted` explicitly rather than rely on
  inference.

### Metadata placement

1. **Use first-class fields first.** Existing fields such as `status`, `protected_data`, `name`, `file_id`, and
   `server_name` are used where they apply. Missing constructor parameters for existing fields are added, such as
   `status` on function calls and results and `name` on data and URI content. No new fields are added for
   provider-specific concepts; the one new field, `hosted`, records a framework decision.
2. **Reserved flat keys have provider-neutral meaning.** Unprefixed keys are reserved for semantics documented by
   core: `model_output_kind` (ADR 0039), and the caller-facing conventions `prompt_cache_breakpoint` and `filename`,
   which applications already set. `filename` remains a supported fallback for `Content.name`.
3. **Provider and protocol data use flat namespaced keys.** Keys have the form `<namespace>.<name>`, such as
   `openai.responses.item_id`, `openai.chat_completions.reasoning_details`, `foundry.reasoning_item`, or
   `ag_ui.thread_id`. Each namespace is documented by one owning package. Other adapters of the same protocol, such as
   hosts implementing Responses, may read and write that package's documented keys. Values are JSON-serializable and
   treated as immutable; code copies composite values before changing them.
4. **Leading-underscore keys are private to core.** Other packages use their namespace. Markers that exist only while
   building a request are never stored on Agent Framework objects.
5. **Persisted replay data is defined per key.** Data that must survive persistence uses `protected_data` for opaque
   provider payloads or a namespaced key whose owner documents its exact shape. The documentation states whether the
   value can contain encrypted or protected data, what is sanitized or excluded, and that only adapters write it.
   Adapters store only fields required for replay, not converted SDK objects, and reject malformed values when
   replaying. `raw_representation` may be used as a fast path only when the persisted path gives the same result or
   fails explicitly.

Flat keys are required because merges are shallow with different conflict rules. A nested per-protocol mapping would
be replaced as a whole, losing fields from earlier fragments or from another producer.

Core documents the reserved flat keys and naming rules in its package documentation. Each namespace owner documents
its keys in its package README, which is published with the package. There is no central allowlist and no runtime
validation; `additional_properties` remains open to applications.

### Compatibility

- Readers accept legacy locations indefinitely. Removing a legacy read is a separate breaking-change decision.
- **Older runtimes cannot read new histories.** `hosted` is a new serialized field, and `Content`'s constructor
  rejects fields it does not know. Once a runtime with this change writes history containing a function call,
  earlier runtimes fail to load that history. Downgrades and mixed-version deployments that share history across
  this boundary are not supported. The implementing change is marked breaking, and its release notes say so.
- For replay-critical keys, writers write both the new and legacy locations until the writing package's next major
  version. This keeps independently versioned packages in one process working, for example an older Hosting
  Responses reading `fc_id`, or older AG-UI, Foundry hosting, and Hosting Responses reading `server_label` from
  content that a newer provider package produced.
- Keys used only for display, diagnostics, or a single request switch directly.

Response-level `additional_properties` are out of scope. `ChatResponse.to_dict()` does not persist them by default,
so preserving response-level metadata would need its own serialization decision. New response-level keys should
nevertheless use the same namespace convention.

### Consequences

- Good, because each identifier has one meaning, and function-call occurrence identity cannot be confused with
  provider identity.
- Good, because approval handling and auto-approval rules depend on an explicit field rather than on the presence
  of a provider string.
- Good, because shared Responses conversion can later rely on one documented set of locations.
- Good, because persisted histories can be replayed after reload, and what they store is explicit.
- Bad, because writers carry duplicated legacy keys until their next major version.
- Bad, because runtimes that predate `hosted` cannot read histories written after the upgrade.
- Bad, because a provider adapter that forgets to set `hosted` makes a hosted call look local; only adapter tests
  catch this.
- Neutral, because existing `Content.id` exceptions remain, although they are now documented and closed.

### Validation

- Each package's tests assert that converting its fixture corpus writes only reserved flat keys, keys in namespaces
  it documents, core-private keys it intentionally sets, and legacy keys it still dual-writes.
- Every replay-critical path has persisted-history fixtures with legacy-only, dual-written, and new-only metadata.
- Replay tests serialize and reload history, so `raw_representation` is absent.
- Core tests cover `hosted` round trips, rejection of non-boolean values, precedence over `server_label`, and legacy
  inference with its warning through the constructor, `from_dict()`, nested approval calls, and pickling.
- Every adapter that parses provider-executed calls or approvals asserts that it sets `hosted=True`. Approval tests in
  core, OpenAI, Foundry hosting, Hosting Responses, and AG-UI cover new and legacy records, including approval-response
  round trips.

## Pros and Cons of the Options

### Document the current keys without changing them

- Good, because nothing changes for users.
- Bad, because approval handling still depends on `server_label`, and replay still depends on raw objects.
- Bad, because nothing prevents the next ad hoc key.

### Add first-class provider identity fields

- Good, because provider item IDs become explicit and typed.
- Bad, because provider concepts enter the provider-neutral core API.
- Bad, because every other provider-specific value would still need a separate rule.

### Store each protocol's metadata in one nested mapping

- Good, because each protocol's metadata sits under one key.
- Bad, because shallow merges replace the whole mapping and lose fields from streamed fragments.
- Bad, because copies share nested mappings, making accidental mutation likely.

### Use existing first-class fields, flat namespaced keys, and reserved flat keys

- Good, because it reuses existing fields and the existing namespaced shell keys.
- Good, because flat keys merge predictably.
- Bad, because it requires migrating existing keys with a compatibility period.

## More Information

### Current keys and targets

This mapping is guidance for implementation and is not exhaustive. "Replay" marks keys covered by the dual-write
rule.

| Current key | Current use | Target | Replay |
| --- | --- | --- | --- |
| `fc_id` | OpenAI function-call item ID; Hosting Responses output item ID | `openai.responses.item_id` | Yes |
| `item_id` | OpenAI hosted custom, tool-search, and function-output item IDs | `openai.responses.item_id` | Yes |
| `item_id` | OpenAI code-interpreter streaming correlation; core fallback | `call_id` | No |
| `status` | OpenAI function-call and reasoning status | `Content.status` | Yes |
| `reasoning_text`, `summary` | OpenAI reasoning replay parts | `openai.responses.*` | Yes |
| `server_label` | Hosted marker and hosted server name on a `function_call` | `hosted=True` and `server_name` | Yes |
| `__foundry_reasoning_replay_item__` | Foundry reasoning item persisted for replay | `foundry.reasoning_item` | Yes |
| `computer_action_format` | OpenAI preview computer-action shape | `openai.responses.computer_action_format` | Yes |
| `openai_content_type` | OpenAI and DevUI input file versus image | `openai.responses.content_type` | Yes |
| `detail` | Image detail written by hosts and read by OpenAI | `openai.image_detail` | Yes |
| `file_id` | Provider file ID on image and screenshot content | `Content.file_id` | Yes |
| `filename` | File name on data and URI content | `Content.name`, with `filename` still read | Yes |
| `openai.local_shell_command_parts` | OpenAI local shell command | `openai.responses.local_shell.command_parts` | Yes |
| `reasoning_details` | Chat Completions reasoning replay on `Message` | `openai.chat_completions.reasoning_details` | Yes |
| `tool_call_index`, `tool_call_choice_index` | Chat Completions streaming aggregation | `openai.chat_completions.*` if persisted; otherwise removed after aggregation | No |
| AG-UI and A2A keys | Approval occurrence, state, display, and metadata | `ag_ui.*` and `a2a.*` if persisted; otherwise not stored on Agent Framework objects | Per key |

Unchanged: `model_output_kind`, `prompt_cache_breakpoint`, `openai.responses.shell.output_type`,
`openai.responses.local_shell.call_item_id`, core-private underscore keys, and the legacy `encrypted_content` read
that now falls back to `protected_data`.

Raw-dependent replay in OpenAI shell handling, Gemini tool-call parts, and the Foundry hosting OAuth fallback moves to
documented replay data under rule 5. Hosting Responses may keep raw output reuse as a fast path.

### Related documents

- [Spec 004: Python function-calling loop](../specs/004-python-function-calling-loop.md)
- [ADR 0039: Preserve model refusals with marked Python text content](0039-python-refusal-content.md)
- [ADR 0043: Preserve host runtime context through MCP invocation and approval](0043-python-mcp-runtime-context.md)
