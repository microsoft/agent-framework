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
| Core guesses stream merge semantics | Providers know whether an event is an incremental delta or a complete snapshot, but that information is discarded before aggregation. Core therefore appends text unconditionally and uses prefix comparison to guess whether code-interpreter content replaces an earlier value, which corrupts repetitive content such as multiple `import` lines. |
| Replay depends on non-persisted objects | OpenAI shell replay, Gemini tool-call parts, Hosting Responses output reuse, and a Foundry hosting OAuth fallback read `raw_representation`, which is absent after history is reloaded. |

Each new provider feature adds another key, and consolidating the duplicated Responses conversions is not possible
while every adapter decides placement independently.

[Spec 004](../specs/004-python-function-calling-loop.md) already defines function-call identity:
`function_call.Content.id` identifies one locally actionable Agent Framework occurrence, while `call_id` is the
provider's call/result correlation. [ADR 0039](0039-python-refusal-content.md) defines the flat
`model_output_kind="refusal"` marker. This decision keeps spec 004's identity semantics and the meaning of ADR
0039's marker unchanged, but moves that marker into the `generic` namespace described below. It also changes which
field marks the hosted server boundary in spec 004's approval scenarios; the implementing change updates spec 004's
hosted-server-boundary scenario row and its authoritative test mapping.

`additional_properties` merges are shallow and not uniform: text, reasoning, and function-call addition keeps the
existing value on collision, the optimized one-pass text and reasoning coalescer independently reproduces that
shallow merge, code-interpreter aggregation keeps the incoming value, and nested values are shared by copies.
Grouping metadata in nested mappings therefore requires changing how core merges and copies them.

## Decision Drivers

- Keep function-call occurrence identity unambiguous and separate from provider identifiers.
- Replay persisted history without `raw_representation`.
- Base core behavior, especially approval handling, on documented first-class fields rather than provider keys.
- Preserve a provider's explicit append-versus-replace intent instead of reconstructing it from payload values.
- Make each provider's metadata explicit and discoverable as a unit, separate from application data.
- Keep existing histories and pending approvals readable after upgrading.
- Keep independently versioned packages working together in one process.
- Keep core provider-neutral and avoid growing `Content` for provider-specific concepts.
- Behave predictably when streamed content is merged and copied.
- Give contributors a rule that is simple to follow and to test.

## Considered Options

1. Document the current keys without changing them.
2. Add first-class provider identity fields, such as `provider_item_id`, to `Content`.
3. Use flat prefixed keys in `additional_properties`, such as `openai.item_id`.
4. Group metadata in nested namespaces in `additional_properties`: one per provider, plus `generic`.

## Decision Outcome

Chosen option: **"Group metadata in nested namespaces in `additional_properties`: one per provider, plus `generic`"**,
combined with using existing first-class fields first. It gives each provider's data one explicit, typed home and
gives provider-neutral semantics a documented place instead of bare top-level names, without adding provider concepts
to core. In exchange, core must merge and copy namespaces one level deep.

### Identity

- `function_call.Content.id` is only the Agent Framework occurrence identity defined by spec 004. Adapters never
  write a provider identifier to it.
- `call_id` is the correlation between a call and its result. When a hosted protocol item exposes only one
  identifier and Agent Framework needs to pair call and result contents, adapters use that identifier as `call_id`.
  This replaces core's code-interpreter fallback on `item_id`.
- A provider item ID that has no first-class field is stored in the provider's namespace, for example
  `additional_properties["openai"]["item_id"]` for OpenAI function calls and function results.
- Existing uses of `Content.id` for a provider identifier remain documented exceptions: reasoning items, computer
  calls and results, and hosted-tool approval requests and responses, which both keep the provider's approval ID so
  the provider can correlate the decision. Local approval requests and responses use the occurrence ID, as spec 004
  defines. New content types do not extend the exceptions without a decision.
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

The exported `ToolApprovalRule` keeps its `server_label` attribute, constructor parameter, and serialized key
unchanged. Only the source of its value changes: new rules take it from the call's `server_name`. Stored standing
rules therefore need no migration, and matching compares a rule's `server_label` with the call's `server_name`.

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
- The server boundary is migrated the same way. When a function call has no `server_name`, the constructor takes it
  from `additional_properties["server_label"]`. When both are present they must be equal; a mismatch is rejected.
  No producer sets `server_name` on function calls today, and new writers dual-write the same value, so a mismatch
  indicates a malformed record rather than one that should be reconciled.
- `Content.from_dict()` builds content through the constructor, so the same inference applies to messages,
  responses, sessions, history providers, harness approval state, and calls nested in approval requests.
- Workflow checkpoints pickle `Content` and restore it through `__setstate__`, which bypasses `from_dict()`.
  `__setstate__` applies the same inference and warning.
- Hosts, AG-UI, and DevUI build content from their own wire formats; they set `hosted` explicitly rather than rely on
  inference.

#### Streaming aggregation

Merging streamed function-call parts rebuilds the content from a fixed list of fields, so the list must include
every first-class field this decision relies on:

- `hosted`: the merged call is hosted if either part is hosted. Parts that do not carry the flag default to local,
  so rejecting differing values would break streams whose argument deltas omit it, and the unsafe error is treating
  a hosted call as local.
- `server_name`: preserved; differing non-empty values are rejected, as for `call_id`.
- `status` on function calls and reasoning: preserved; the latest non-empty value wins, because status progresses
  during a stream, for example from `in_progress` to `completed`.

PR [#8953](https://github.com/microsoft/agent-framework/pull/8953) already makes text and reasoning coalescing
linear; this decision standardizes merge meaning rather than adding another performance mechanism.

All content types that core can aggregate get an explicit first-class
`merge_mode: Literal["append", "replace"] | None` field. This initially covers `text`, `text_reasoning`,
`function_call`, `usage`, `code_interpreter_tool_call`, and `code_interpreter_tool_result`.

- The mode belongs to the incoming stream fragment. It is not provider metadata and does not participate in
  identifying which logical item the fragment belongs to. Core first applies the existing type-specific identity
  and adjacency rules, then applies the fragment's mode.
- Direct `Content.__add__` and optimized response coalescers honor the same modes. Constructors reject a non-`None`
  mode on content types that core does not aggregate.
- `append` uses the content type's existing incremental merge. `replace` treats the incoming semantic payload as a
  complete snapshot and replaces the accumulated payload for that logical item. Stable identity and correlation
  fields are still validated, while status and namespaced metadata follow their separate merge rules.
- Providers set a mode on every mergeable streamed item they produce. Delta events use `append`; complete or
  `*.done` snapshots use `replace`. Core does not use prefix comparison or another payload heuristic when a mode is
  present.
- `None` means legacy behavior, not `append`. This keeps older provider packages working on a newer core: text,
  reasoning, function calls, and usage retain their current type-specific behavior, and code-interpreter content
  retains its current prefix inference. Removing that fallback is a separate compatibility decision after supported
  providers no longer emit unmarked fragments.
- The field is serialized so individually persisted updates retain their merge semantics. Aggregation consumes it;
  finalized `ChatResponse` and `AgentResponse` content has `merge_mode=None`, so an operational stream instruction
  does not become part of persisted logical history.
- This is one field interpreted by the existing type-specific merge code. It does not introduce merge strategy
  objects, a registry, or provider callbacks.

### Metadata placement

```python
content.additional_properties == {
    "generic": {"model_output_kind": "refusal"},     # provider-neutral, documented by core
    "openai": {"item_id": "fc_123"},                 # owned by agent-framework-openai
    "foundry": {"reasoning_item": {...}},            # owned by agent-framework-foundry
    "_approval_request_id": "...",                   # core-private, unchanged
    "ticket": "ABC-42",                              # application data, unchanged
}
```

1. **Use first-class fields first.** Existing fields such as `status`, `protected_data`, `name`, `file_id`, and
   `server_name` are used where they apply. Missing constructor parameters for existing fields are added, such as
   `status` on function calls, function results, and reasoning, and `name` on data and URI content. No new fields are
   added for provider-specific concepts; the new `hosted` and `merge_mode` fields record framework behavior.
2. **Provider data lives in the provider's namespace.** `additional_properties["<namespace>"]` is a mapping owned by
   one integration package and named after it: `openai`, `foundry`, `anthropic`, `gemini`, `bedrock`, `a2a`,
   `ag_ui`, and so on. Data for a wire protocol belongs to the package that owns that protocol's mapping: Foundry chat
   and the hosts that implement Responses read and write `openai` for Responses data, and Foundry keeps Foundry-only
   data under `foundry`. Each owner documents its keys in its package README and may publish a `TypedDict` for its
   namespace and small accessor functions.
3. **Provider-neutral data lives in `generic`.** `additional_properties["generic"]` holds semantics documented by
   core that any package may read or write: `model_output_kind` from ADR 0039 and the caller-facing
   `prompt_cache_breakpoint`. Only core adds keys to `generic`. File names use the first-class `Content.name` field.
4. **Namespaces are exactly one level deep.** A namespace maps flat key names to plain JSON values (mappings, lists,
   strings, numbers, booleans, and `None`), never dataclass or Pydantic instances, because `Content.from_dict()` does
   not reconstruct arbitrary types. An owner that implements several protocols qualifies key names where needed rather
   than adding another level. Values inside a namespace are opaque to merging and treated as immutable.
5. **Other top-level keys.** Leading-underscore keys remain core-private at the top level. Keys defined by other
   decisions, such as the security labels of ADR 0024, are not moved by this decision. Markers that exist only while
   building a request are never stored on Agent Framework objects. All other top-level keys belong to applications;
   `generic` and the namespace names are reserved.
6. **Persisted replay data is defined per key.** Data that must survive persistence uses `protected_data` for opaque
   provider payloads or a namespace key whose owner documents its exact shape. The documentation states whether the
   value can contain encrypted or protected data, what is sanitized or excluded, and that only adapters write it.
   Adapters store only fields required for replay, not converted SDK objects, and reject malformed values when
   replaying. `raw_representation` may be used as a fast path only when the persisted path gives the same result or
   fails explicitly.

#### Merging and copying namespaces

With today's shallow merges, a namespace would be replaced as a whole, losing fields from earlier stream fragments or
from another producer. Core therefore changes how `additional_properties` are combined and copied:

- One core merge function combines two mappings. When both hold a mapping under the same top-level key, it merges
  them one level deep. Each merge site keeps its existing conflict rule for colliding keys: content addition keeps
  the existing value; code-interpreter and response aggregation keep the incoming value.
- Every core merge site uses it: direct content addition, one-pass text and reasoning coalescing, code-interpreter
  aggregation, response aggregation, workflow-agent response merging, and function-result carriers. Packages that
  merge metadata themselves, such as A2A combining task metadata, use it too.
- The rule applies to any top-level mapping, not only known namespace names, because core cannot list every
  third-party provider. Application values that are mappings therefore also merge one level deep when streamed
  fragments are combined, instead of being replaced.
- `Content` and `Message` constructors copy namespace mappings one level, so constructed objects don't share them.
  Writers never change a namespace in place; they replace it with an updated copy. Core provides small public helpers
  to read a namespaced value and to store an updated copy, so providers outside this repository follow the same rule.
- Compaction's token estimation strips opaque values inside namespaces as well as at the top level. Today it removes
  only a top-level `encrypted_content`, so the encrypted payload inside Foundry's persisted reasoning item is counted.

Core documents `generic`, the namespace rules, and the merge behavior in its package documentation. There is no
central allowlist and no runtime validation; `additional_properties` remains open to applications outside the
reserved names.

### Compatibility

- Readers accept legacy locations indefinitely. Removing a legacy read is a separate breaking-change decision.
- **Upgrading is safe; downgrading is not.** New runtimes read every existing history: content written before this
  change, with or without `server_label`, loads through the legacy inference and legacy key reads described above.
  The break is in the other direction: `hosted` and `merge_mode` are new serialized fields, and `Content`'s
  constructor rejects fields it does not know, so runtimes that predate this change fail to load records a new
  runtime wrote while either field is present. Aggregated logical history clears `merge_mode`, but persisted
  individual updates can contain it. Downgrades and mixed-version deployments that share records across this
  boundary are not supported. The implementing change is marked breaking for that reason, and its release notes say
  that existing histories remain readable after upgrading.
- For replay-critical keys, writers write both the new and legacy locations until the writing package's next major
  version. This keeps independently versioned packages in one process working, for example an older Hosting
  Responses reading `fc_id`, or older AG-UI, Foundry hosting, and Hosting Responses reading `server_label` from
  content that a newer provider package produced.
- `model_output_kind` and `prompt_cache_breakpoint` move into `generic`; their meaning is unchanged. Readers accept the
  flat keys indefinitely, writers write both until their next major version, and applications that set the flat keys
  keep working. ADR 0039 remains the record of the refusal decision.
- A package that writes namespaces requires, as its minimum core version, the core release that merges them. On an
  older core, streamed fragments would lose namespace fields during aggregation.
- Keys used only for display, diagnostics, or a single request switch directly.

Response-level `additional_properties` are out of scope. `ChatResponse.to_dict()` does not persist them by default,
so preserving response-level metadata would need its own serialization decision. New response-level keys should
nevertheless use the same namespaces; response aggregation uses the namespace-aware merge, so they combine safely.

### Consequences

- Good, because each identifier has one meaning, and function-call occurrence identity cannot be confused with
  provider identity.
- Good, because approval handling and auto-approval rules depend on an explicit field rather than on the presence
  of a provider string.
- Good, because each provider's metadata sits under one explicit key that can be typed as one `TypedDict`, inspected,
  or stripped as a unit, and is visibly separate from application data.
- Good, because provider-neutral semantics have one documented home instead of competing with application keys.
- Good, because aggregation uses provider-declared delta or snapshot semantics instead of guessing from payload
  prefixes.
- Good, because shared Responses conversion can later rely on one documented set of locations.
- Good, because persisted histories can be replayed after reload, and what they store is explicit.
- Bad, because core's merge behavior changes at every merge site, including for application values that are mappings.
- Bad, because writers must replace namespaces rather than mutate them; a writer that mutates in place corrupts
  metadata shared with copies. The core helpers make the safe path easy but cannot enforce it.
- Bad, because core gains public helper functions, and writer packages must raise their minimum core version.
- Bad, because ADR 0039's marker and the caller-facing `prompt_cache_breakpoint` move, so samples and documentation
  change, although the flat keys remain readable.
- Bad, because `generic` and every namespace name become reserved top-level keys. No collisions exist in this
  repository, but applications outside it could already use those names.
- Bad, because writers carry duplicated legacy keys until their next major version.
- Bad, because runtimes that predate either new field cannot read records that still contain that field, although
  upgraded runtimes read all existing records.
- Bad, because `Content` gains an operational field that is meaningful only before aggregation; clearing it from
  finalized content keeps that concern from leaking further.
- Bad, because every provider that emits mergeable stream content must classify its events, and a wrong `replace`
  marker discards accumulated payload while a wrong `append` marker can duplicate a snapshot.
- Bad, because unmarked code-interpreter content retains the legacy prefix heuristic during compatibility, so the
  corruption fixed by explicit modes remains possible with an older provider package.
- Bad, because a provider adapter that forgets to set `hosted` makes a hosted call look local; only adapter tests
  catch this.
- Neutral, because existing `Content.id` exceptions remain, although they are now documented and closed.

### Validation

- Each package's tests assert that converting its fixture corpus writes only keys in its own namespace, documented
  `generic` keys, core-private keys it intentionally sets, and legacy keys it still dual-writes.
- Core tests cover namespace merging at each merge site with both conflict rules, one-level depth, non-mapping values
  under a namespace name, constructor copying, the helpers' copy-on-write behavior, and compaction stripping opaque
  values inside namespaces.
- OpenAI and Foundry streaming tests merge fragments whose namespaces carry different keys and assert that none is
  lost.
- Every replay-critical path has persisted-history fixtures with legacy-only, dual-written, and new-only metadata.
- Replay tests serialize and reload history, so `raw_representation` is absent.
- Core tests cover `hosted` round trips, rejection of non-boolean values, precedence over `server_label`, and legacy
  inference with its warning through the constructor, `from_dict()`, nested approval calls, and pickling. They also
  cover filling `server_name` from `server_label` and rejecting records where the two differ.
- Streaming aggregation tests merge function-call and reasoning parts and assert that `hosted`, `server_name`, and
  `status` survive, following the rules above.
- For every mergeable content type, contract tests split a known payload into different append fragments, optionally
  follow them with a replace snapshot, and assert exact reconstruction through both `ChatResponse.from_updates()` and
  streaming `get_final_response()`. Tests include repetitive and prefix-shaped fragments, serialization of
  unaggregated updates, rejection of invalid modes and unsupported content types, clearing the mode on finalized
  content, and the legacy unmarked behavior.
- Harness tests load standing `ToolApprovalRule` state written before the change and confirm it still matches hosted
  calls from the same server, and never matches a local call with the same name and arguments.
- Every adapter that parses provider-executed calls or approvals asserts that it sets `hosted=True`. Approval tests in
  core, OpenAI, Foundry hosting, Hosting Responses, and AG-UI cover new and legacy records, including approval-response
  round trips that keep the provider approval ID.

## Pros and Cons of the Options

### Document the current keys without changing them

- Good, because nothing changes for users.
- Bad, because approval handling still depends on `server_label`, and replay still depends on raw objects.
- Bad, because nothing prevents the next ad hoc key.

### Add first-class provider identity fields

- Good, because provider item IDs become explicit and typed.
- Bad, because provider concepts enter the provider-neutral core API.
- Bad, because every other provider-specific value would still need a separate rule.

### Use flat prefixed keys

- Good, because existing shallow merges keep working unchanged and no core helpers are needed.
- Good, because it extends the existing `openai.responses.*` shell keys.
- Bad, because a provider's data is spread across many top-level keys mixed with application data, and cannot be
  typed, inspected, or stripped as a unit.
- Bad, because provider-neutral keys would stay as bare top-level names that compete with application keys.

### Group metadata in nested namespaces, one per provider plus `generic`

- Good, because each provider's metadata is explicit, typed, and separable from application data.
- Good, because provider-neutral semantics have a documented home.
- Bad, because core merges must become namespace-aware, writers must copy on write, and writer packages need a newer
  core.
- Bad, because it requires migrating existing keys with a compatibility period.

## More Information

### Current keys and targets

This mapping is guidance for implementation and is not exhaustive. `openai["item_id"]` is short for
`additional_properties["openai"]["item_id"]`. "Replay" marks keys covered by the dual-write rule.

| Current key | Current use | Target | Replay |
| --- | --- | --- | --- |
| `fc_id` | OpenAI function-call item ID; Hosting Responses output item ID | `openai["item_id"]` | Yes |
| `item_id` | OpenAI hosted custom, tool-search, and function-output item IDs | `openai["item_id"]` | Yes |
| `item_id` | OpenAI code-interpreter streaming correlation; core fallback | `call_id` | No |
| `status` | OpenAI function-call and reasoning status | `Content.status`, with new constructor parameters | Yes |
| `reasoning_text`, `summary` | OpenAI reasoning replay parts | `openai["reasoning_text"]`, `openai["summary"]` | Yes |
| `server_label` | Hosted marker and hosted server name on a `function_call` | `hosted=True` and `server_name`; `ToolApprovalRule.server_label` is unchanged | Yes |
| `model_output_kind` | Refusal marker from ADR 0039 | `generic["model_output_kind"]` | Yes |
| `prompt_cache_breakpoint` | Caller-set prompt-cache boundary | `generic["prompt_cache_breakpoint"]`, with the flat key still read | Yes |
| `__foundry_reasoning_replay_item__` | Foundry reasoning item persisted for replay | `foundry["reasoning_item"]` | Yes |
| `computer_action_format` | OpenAI preview computer-action shape | `openai["computer_action_format"]` | Yes |
| `openai_content_type` | OpenAI and DevUI input file versus image | `openai["content_type"]` | Yes |
| `detail` | Image detail written by hosts and read by OpenAI | `openai["image_detail"]` | Yes |
| `file_id` | Provider file ID on image and screenshot content | `Content.file_id` | Yes |
| `filename` | File name on data and URI content | `Content.name`, with the flat key still read | Yes |
| `openai.responses.shell.output_type` | OpenAI shell output type | `openai["shell_output_type"]` | Yes |
| `openai.responses.local_shell.call_item_id` | OpenAI local shell call item ID | `openai["local_shell_call_item_id"]` | Yes |
| `openai.local_shell_command_parts` | OpenAI local shell command | `openai["local_shell_command_parts"]` | Yes |
| `reasoning_details` | Chat Completions reasoning replay on `Message` | `openai["reasoning_details"]` | Yes |
| `tool_call_index`, `tool_call_choice_index` | Chat Completions streaming aggregation | `openai[...]` if persisted; otherwise removed after aggregation | No |
| AG-UI and A2A keys | Approval occurrence, state, display, and metadata | `ag_ui[...]` and `a2a[...]` if persisted; otherwise not stored on Agent Framework objects | Per key |

Unchanged: core-private underscore keys, the security keys defined by ADR 0024, and the legacy `encrypted_content`
read that now falls back to `protected_data`.

Raw-dependent replay in OpenAI shell handling, Gemini tool-call parts, and the Foundry hosting OAuth fallback moves to
documented replay data under rule 5. Hosting Responses may keep raw output reuse as a fast path.

### Related documents

- [Spec 004: Python function-calling loop](../specs/004-python-function-calling-loop.md)
- [ADR 0039: Preserve model refusals with marked Python text content](0039-python-refusal-content.md)
- [ADR 0043: Preserve host runtime context through MCP invocation and approval](0043-python-mcp-runtime-context.md)
- [Issue 8910: Explicit append/replace semantics for streamed content merging](https://github.com/microsoft/agent-framework/issues/8910)
- [Issue 8903: Streamed code-interpreter code can be corrupted by prefix inference](https://github.com/microsoft/agent-framework/issues/8903)
