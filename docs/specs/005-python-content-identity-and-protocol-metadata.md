---
status: approved
contact: eavanvalkenburg
deciders: eavanvalkenburg
---

# Python content identity and protocol metadata contract

## Scope

This specification defines the serialized Python contract selected by
[ADR 0044](../decisions/0044-python-content-identity-and-protocol-metadata.md). It applies to `Content`, `Message`,
streamed response aggregation, and all Python provider and protocol adapters that emit or consume these values,
including OpenAI, Foundry, Anthropic, Bedrock, Gemini, Mistral, Ollama, Claude, GitHub Copilot, Copilot Studio,
Hosting Responses, Hosting A2A, DevUI, AG-UI, and A2A.

The contract has four parts:

1. Message identity, Agent Framework content occurrence identity, provider item identity, and call correlation remain
   separate.
2. Execution routing and stream merge intent use first-class fields.
3. Provider-neutral and provider-owned metadata use one-level namespaces.
4. Legacy locations remain readable; replay-critical writers temporarily dual-write.

This specification is normative. Package documentation may describe individual keys but must not define conflicting
locations or merge behavior.

## First-class fields

### Function-call and result identity

| Field | Content types | Meaning |
| --- | --- | --- |
| `Content.id` | `function_call` | Agent Framework identity for one actionable occurrence. It is never an OpenAI or other provider item ID. |
| `Content.id` | `function_result` | The function-call occurrence settled by the result, when known. |
| `Content.call_id` | Calls and results | Provider/service call-result correlation. It may be reused in a later occurrence. |
| `Content.id` | Reasoning, computer use, hosted approval controls | Existing documented provider-identity exception. New content types do not create more exceptions. |

An occurrence-identified Host result binds to that exact occurrence. An id-less Host result is a compatibility form
and binds only when the active batch has one unambiguous unanswered occurrence with the same `call_id`.

### Message identity and metadata

`Message.message_id`, `ChatResponseUpdate.message_id`, and `AgentResponseUpdate.message_id` identify the containing
provider or protocol message. They do not identify a `Content` item and must not be substituted for `Content.id` or
`call_id`.

When streamed updates carry a non-empty `message_id`, aggregation preserves it on the finalized `Message`. A change
between two non-empty message IDs starts a new message; an absent ID keeps the legacy role-and-adjacency grouping.
Adapters preserve a provider message ID when the protocol exposes one. Deserializing an older message without an ID
does not manufacture one.

Message- and update-level `additional_properties` follow the same namespace rules as content metadata. A protocol's
message metadata belongs in that protocol owner's namespace; content item metadata remains on the relevant `Content`.

`ChatResponseUpdate.merge_mode` and `AgentResponseUpdate.merge_mode` apply to the containing logical message. An
incoming `replace` update clears the accumulated contents of the message selected by `message_id` and role before
the update's contents are applied. `append` and `None` retain the existing accumulation behavior. Protocols must use
update-level replacement for authoritative heterogeneous message or artifact snapshots whose prior URI, binary, or
other non-mergeable content must be discarded.

### Hosted execution

`function_call` content serializes:

```json
{
  "type": "function_call",
  "call_id": "call_123",
  "id": "occurrence_123",
  "hosted": true,
  "server_name": "mcp_server"
}
```

- `hosted=True` means the provider or service executes the call. Agent Framework must not execute it locally.
- `hosted=False` means the call is locally actionable.
- `server_name` is the descriptive hosted-server boundary. It does not decide routing.
- `hosted` is valid only on `function_call` content and must be a boolean when supplied. Construction normalizes an
  omitted value to `False` unless the legacy migration below infers `True`; serialization always writes a boolean.
- A streamed call consists of complete `Content` fragments; the wire does not split or incrementally deserialize the
  boolean itself. Fragments can still differ because argument-only deltas may omit hosted ownership and therefore
  normalize to `False`. Aggregation uses logical OR so a fragment that established `hosted=True` cannot later become
  locally actionable. Conflicting non-empty `server_name` values are rejected.

Legacy `additional_properties["server_label"]` remains readable. When first-class `hosted` is absent, a truthy
string `server_label` infers `hosted=True`, fills a missing `server_name`, and emits `FutureWarning`. This compatibility
inference uses only the legacy `server_label`; first-class `server_name` never implies hosted ownership. When
`hosted` and legacy `server_label` are both absent, `hosted` becomes `False` even if `server_name` is present. When
both server names are present they must match. The same migration runs through construction, `from_dict()`, nested
approval content, and pickle restoration.

`ToolApprovalRule.server_label` remains public API and persisted state. New rules source its value from
`function_call.server_name`.

### Stream merge intent

The following content types accept
`merge_mode: Literal["append", "replace"] | None`:

- `text`
- `text_reasoning`
- `function_call`
- `usage`
- `code_interpreter_tool_call`
- `code_interpreter_tool_result`

URI, data, image, audio, and other non-mergeable content types are atomic values: adapters emit a complete item
rather than fragments of a URL or base64 payload. They therefore do not accept content-level `merge_mode`. When an
authoritative protocol snapshot replaces a heterogeneous message containing those items, the adapter uses the
update-level replacement described above.

The mode belongs to the incoming fragment:

- `append` applies the content type's incremental merge.
- `replace` makes the incoming semantic payload authoritative after identity validation.
- `None` preserves the legacy type-specific behavior.

`None` is not an alias for `replace`, and there is no single universal implicit default. It delegates to the behavior
that existed before `merge_mode`: text and reasoning text concatenate, function-call fields and arguments merge
incrementally, usage values add, and code-interpreter inputs and outputs use their existing field-wise list merge.
This compatibility mode exists for older adapters; new provider updates must state `append` or `replace` explicitly.

Content-level modes are serialized on individual content items. Update-level modes are serialized on
`ChatResponseUpdate` and `AgentResponseUpdate`. `ChatResponse.from_updates()`,
`AgentResponse.from_updates()`, and `ResponseStream.get_final_response()` consume update-level modes and recursively
clear content-level modes from finalized content, including nested content items.

Providers must mark every mergeable streamed item they emit. Delta events use `append`; authoritative payload
snapshots use `replace`. An event name such as `*.done` does not by itself imply replacement when the event carries
only final metadata and omits an earlier streamed payload. Unreleased `stream_complete` and `complete` metadata
markers are not compatibility formats.

## Metadata namespaces

`additional_properties` reserves:

- `core`: provider-neutral semantics documented by core;
- a provider/protocol owner name such as `openai`, `foundry`, or `a2a`;
- leading-underscore top-level keys for core-private state.

For a package-owned namespace, the canonical key is the normalized integration package suffix: remove the
`agent-framework-` prefix and replace hyphens with underscores, for example `agent-framework-ag-ui` uses `ag_ui` and
`agent-framework-github-copilot` uses `github_copilot`. A package implementing another owner's wire protocol uses that
protocol owner's namespace instead and documents the exception; for example Foundry and hosting packages use
`openai` for Responses metadata and `foundry` only for Foundry-owned data.

Namespace values are mappings with one level of keys. Each value must be plain serializable data. A value may itself
be a JSON mapping or list, but namespace owners do not add a second namespace layer.

Example:

```json
{
  "core": {"model_output_kind": "refusal"},
  "openai": {"item_id": "fc_123", "image_detail": "high"},
  "_approval_request_id": "approval_123",
  "application_ticket": "ABC-42"
}
```

### Exact mapping

| Owner | Content/message | Legacy location | Canonical location | Compatibility |
| --- | --- | --- | --- | --- |
| core | refusal text | `model_output_kind` | `core["model_output_kind"]` | Read indefinitely; dual-write through the writer package's next major version. |
| core/OpenAI | input content | `prompt_cache_breakpoint` | `core["prompt_cache_breakpoint"]` | Read indefinitely; dual-write through the OpenAI package's next major version. |
| OpenAI | function call/result and provider output items | `fc_id` or `item_id` | `openai["item_id"]` | Read indefinitely; dual-write when persisted replay or an independently versioned host consumes the value. |
| OpenAI | input image/file discriminator | `openai_content_type` | `openai["content_type"]` | Read indefinitely; dual-write through the writer package's next major version. |
| OpenAI | image input/screenshot | `detail` | `openai["image_detail"]` | Read indefinitely; dual-write through the writer package's next major version. |
| OpenAI | computer call | `computer_action_format` | `openai["computer_action_format"]` | Read indefinitely; dual-write through the writer package's next major version. |
| OpenAI | text output | `logprobs` | `openai["logprobs"]` | Read indefinitely; dual-write when the content can cross package boundaries. |
| OpenAI | reasoning summary marker | `reasoning_text` | `openai["reasoning_text"]` | Read indefinitely; dual-write for persisted replay. |
| OpenAI | Chat Completions message | `reasoning_details` | `openai["reasoning_details"]` | Read indefinitely. Provider-emitted opaque reasoning payloads use `Content.protected_data`. |
| OpenAI | shell tool declaration | `openai.responses.shell.environment` | `openai["shell_environment"]` | Read indefinitely; dual-write for replay. |
| OpenAI | shell result | `openai.responses.shell.output_type` | `openai["shell_output_type"]` | Read indefinitely; dual-write for replay. |
| OpenAI | local shell result | `openai.responses.local_shell.call_item_id` | `openai["local_shell_call_item_id"]` | Read indefinitely; dual-write for replay. |
| OpenAI | local shell call/result | `openai.local_shell_command_parts` | `openai["local_shell_command_parts"]` | Read indefinitely; dual-write for replay. |
| OpenAI | OAuth consent request server | `server_label` | `openai["server_label"]` | Read indefinitely; dual-write through the writer package's next major version. |
| Foundry | reasoning content | `__foundry_reasoning_replay_item__` | `foundry["reasoning_item"]` | Read indefinitely; dual-write through the Foundry package's next major version. |
| Bedrock | redacted reasoning marker | `bedrock.redacted_reasoning` | `bedrock["redacted_reasoning"]` | Read indefinitely; dual-write through the Bedrock package's next major version. |
| Mistral | response service tier | `service_tier` | `mistral["service_tier"]` | Read indefinitely; dual-write through the Mistral package's next major version. |
| A2A | response/update/message metadata | `a2a_metadata` | `a2a` | Read indefinitely with a warning for legacy-only input; dual-write through the A2A package's next major version. |
| all | data/URI/hosted-file display name | `filename` | `Content.name` | Read indefinitely where accepted; dual-write where older adapters require it. |
| all | data/URI provider file identity | `file_id` | `Content.file_id` | Read indefinitely where accepted; dual-write where older adapters require it. |
| all | function/reasoning/tool status | `additional_properties["status"]` | `Content.status` | Read indefinitely where accepted; new writers use the field. |
| hosted adapters | hosted routing | `server_label` | `Content.hosted` plus `Content.server_name` | Constructor migration as defined above; replay-critical writers dual-write. |

OpenAI reasoning item IDs, computer call/result IDs, and hosted approval request/response IDs retain their documented
`Content.id` exception. The table does not move core-private keys, security labels, or application metadata.

## Merge and copy behavior

Core exposes:

```python
get_namespaced_value(additional_properties, namespace, key, default=None)
with_namespaced_value(additional_properties, namespace, key, value)
merge_additional_properties(existing, incoming, *, incoming_wins=True)
```

- Constructors copy the top-level mapping and every top-level mapping value.
- Writers replace a namespace with a copied mapping; they do not mutate a shared nested mapping.
- When both sides contain mappings under the same top-level key, merging combines those mappings one level deep.
- Other values remain opaque.
- Direct content addition keeps existing values on collision.
- Response, workflow response, function-result carrier, and code-interpreter aggregation keep incoming values.
- The rule applies to application-owned top-level mappings as well as reserved namespaces.

## Replay and protected data

- Replay must not depend on `raw_representation`; it is absent after persisted history reload.
- Replay-critical namespace values contain only the minimum plain data needed to reconstruct the provider item.
- Opaque provider reasoning payloads use `Content.protected_data` when that field applies.
- Compaction token estimation removes `encrypted_content` recursively, including inside provider namespace values.
- Adapters reject malformed replay metadata instead of silently emitting a different provider transcript.

## Version compatibility

- Upgrades read old histories.
- Downgrades across this change are unsupported because older runtimes reject serialized `hosted` and `merge_mode`.
- Legacy reads remain until a separate breaking decision removes them.
- Replay-critical writers dual-write until that package's next major version. Display-only or request-local keys may
  switch immediately.
- The owning integration package centralizes its canonical and legacy keys and may warn when it consumes legacy-only
  input. Generic core namespace helpers do not contain provider-specific migration tables.
- A package that writes namespaces requires a core version that implements one-level namespace merging.

## Authoritative validation

| Contract | Authoritative tests |
| --- | --- |
| Field validation, serialization, legacy hosted inference, namespace helpers, one-level merge rules, merge modes, and finalization | `python/packages/core/tests/core/test_types.py` |
| Compaction strips opaque nested values | `python/packages/core/tests/core/test_compaction.py` |
| Occurrence-aware approval and Host-result matching | Scenario rows in [spec 004](004-python-function-calling-loop.md), primarily `python/packages/core/tests/core/test_function_invocation_logic.py` |
| OpenAI Responses mappings, done snapshots, hosted approvals, shell replay, and persisted-history replay | `python/packages/openai/tests/openai/test_openai_chat_client.py` |
| OpenAI Chat Completions generic/OpenAI metadata and streamed merge modes | `python/packages/openai/tests/openai/test_openai_chat_completion_client.py` |
| Foundry reasoning replay | `python/packages/foundry/tests/foundry/test_foundry_chat_client.py` |
| Foundry hosting conversion and hosted routing | `python/packages/foundry_hosting/tests/test_responses.py` |
| Hosting Responses parsing/rendering | `python/packages/hosting-responses/tests/hosting_responses/test_parsing.py` |
| DevUI Responses conversion | `python/packages/devui/tests/devui/test_conversations.py`, `python/packages/devui/tests/devui/test_mapper.py` |
| AG-UI stream merge modes, hosted/local ownership, and approval replay | `python/packages/ag-ui/tests/ag_ui/test_event_converters.py`, `test_run.py`, `test_workflow_run.py`, and `test_endpoint.py` |
| A2A stream merge modes and namespaced metadata round trip | `python/packages/a2a/tests/test_a2a_agent.py` |
| Hosting A2A message metadata conversion | `python/packages/hosting-a2a/tests/hosting_a2a/test_conversion.py` |
| Anthropic streamed merge modes and provider-hosted tool routing | `python/packages/anthropic/tests/test_anthropic_client.py` |
| Bedrock streamed merge modes and redacted-reasoning replay metadata | `python/packages/bedrock/tests/test_bedrock_client.py` |
| Gemini streamed merge modes and persisted provider-hosted tool replay | `python/packages/gemini/tests/test_gemini_client.py` |
| Mistral streamed merge modes and response metadata | `python/packages/mistral/tests/mistral/test_mistral_chat_client.py` |
| Ollama streamed merge modes | `python/packages/ollama/tests/test_ollama_chat_client.py` |
| Claude managed-agent streamed merge modes | `python/packages/claude/tests/test_claude_agent.py` |
| GitHub Copilot streamed merge modes and provider-hosted tool routing | `python/packages/github_copilot/tests/test_github_copilot_agent.py` |
| Copilot Studio streamed merge modes | `python/packages/copilotstudio/tests/test_copilot_agent.py` |

Every changed package must test legacy-only, dual-written, and canonical-only inputs for replay-critical mappings.
Streaming tests must cover repetitive fragments and snapshots whose text begins with the accumulated prefix, so tests
verify explicit merge intent rather than a prefix heuristic.
