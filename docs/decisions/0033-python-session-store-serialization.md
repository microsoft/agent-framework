---
status: proposed
contact: eavanvalkenburg
date: 2026-07-24
deciders: eavanvalkenburg, chetantoshnival, taochenosu, moonbox3, giles17
---

# Python session storage and serialization

## Context and Problem Statement

Python does not have a broadly shared session-store API in
`agent-framework-core`. The alpha `agent-framework-hosting` package has a small process-local `SessionStore`, but that
type is hosting-specific, in-memory only, and unavailable to packages such as Foundry Hosting without taking a
dependency on the hosting helper package.

The alpha implementation is a prototype, not a compatibility constraint. This decision may replace its location,
names, method shape, and behavior if another design is preferable.

The existing file-backed persistence surfaces solve narrower problems:

- `FileHistoryProvider` stores conversation `Message` records, not complete `AgentSession` snapshots;
- `FileCheckpointStorage` stores workflow checkpoints; and
- the Responses provider stores protocol history, but not Agent Framework runtime state carried in
  `AgentSession.state`.

`AgentSession.to_dict()` / `from_dict()` already provide a dictionary snapshot shape. Session state may contain
framework or application-defined objects, and `register_state_type` provides dynamic type restoration, but the
registration and collision behavior is not yet strong enough to serve as a durable, cold-start persistence contract.

The framework therefore needs to decide:

- where a reusable in-memory and file-backed session store belongs;
- how a complete `AgentSession` should be serialized atomically and validated;
- how custom nested state types are registered and restored after process restart; and
- how to provide the required readable JSON format while leaving room for an optional optimized binary format.

## Decision Drivers

### Session-store ownership and API

- Make session storage reusable by core, hosting, and provider packages without creating dependency cycles.
- Keep the smallest public API that supports in-memory use, durable implementations, and application-defined stores.
- Define the minimum async operations required for lookup, replacement, and deletion.
- Decide explicitly whether reads return shared instances or independent snapshots suitable for branching.
- Simpler is better

### Serialization and type restoration

- Provide readable JSON serialization as a required capability.
- Treat an optimized binary format as a nice-to-have only when the chosen JSON implementation supports it without a
  separate state model or substantial additional complexity.
- Perform one typed encode and decode operation per file write/read.
- Preserve existing dynamic application registration of nested state types.
- Fail before persistence when an object cannot be restored after a cold start.
- Keep the existing serialized `{"type": "<id>", ...}` representation compatible.

## Decision 1: Session-store ownership and API shape

### Keep `SessionStore` in `agent-framework-hosting`

- Good: keeps the abstraction local to app-owned hosting scenarios.
- Bad: Foundry Hosting and other packages cannot reuse it without depending on the hosting helper package.
- Bad: a generic session snapshot store is not inherently or only a web-hosting concern.
- Bad: durable implementations would either be duplicated or placed in an unrelated package.

### Add an abstract store plus separate in-memory and file implementations

For example, define a `SessionStore` protocol/ABC with `InMemorySessionStore` and `FileSessionStore`.

- Good: clearly separates the contract from implementations.
- Good: implementation names state their storage behavior explicitly.
- Neutral: follows a familiar repository/adapter pattern.
- Bad: introduces an additional public type and rename for a three-method experimental API.
- Bad: callers must choose an implementation even for the default in-memory case.
- Bad: the abstraction adds little value while every implementation still needs the same method overrides.

### Move the concrete store to core and use it as the overridable base

Move `SessionStore` to `agent-framework-core`, retain its in-memory behavior, and implement `FileSessionStore` by
overriding the same async methods.

- Good: one public type is both the useful default and the extension point.
- Good: existing custom stores can continue subclassing and overriding `get` / `set` / `delete`.
- Good: core and provider packages can share the API without depending on hosting helpers.
- Good: `FileSessionStore` remains a focused subclass while the base stays free of file-system concerns.
- Bad: the class name does not explicitly say "in memory" when used without overrides.

## Decision 2: Serialization and type restoration

Once a file-backed store exists, it needs an on-disk format and a reliable way to reconstruct the complete
`AgentSession`, including nested framework and application-defined state. This decision is independent of where the
store API lives or whether that API is abstract or concrete.

The alternatives below compare top-level snapshot validation, JSON encoding/decoding cost, and how each option
interacts with the dynamic custom-state registry. Binary storage is not a primary selection criterion.

### Considered options

The standard-library and optimized-JSON options are not mutually exclusive. A store can default to `json` while
accepting caller-supplied `dumps` / `loads` callables for `orjson` or another compatible implementation. This is the
pre-msgspec `FileHistoryProvider` design; those hooks remain only as a deprecated compatibility path.

### Standard library `json`

- Good: no additional dependency and familiar readable output.
- Good: accepts the existing dictionary snapshots without a schema.
- Good: can remain the fallback/default behind pluggable `dumps` / `loads`.
- Neutral: custom state restoration still requires the framework registry.
- Bad: slower encoding and decoding than optimized native implementations.
- Bad: provides no typed snapshot validation during file reads.

### Optimized drop-in JSON libraries such as `orjson`

- Good: substantially faster JSON encoding and decoding than the standard library.
- Good: can preserve the existing dictionary-oriented snapshot and custom `dumps` / `loads` shape.
- Good: can be an opt-in codec without making the optimized package a framework dependency.
- Neutral: returns bytes when encoding, which the file stores can already handle.
- Neutral: custom state restoration still requires the framework registry.
- Bad: remains an untyped top-level decode; the framework must separately validate the session snapshot shape.
- Bad: choosing one drop-in implementation as a core dependency adds a dependency without providing typed construction.

### Pydantic `model_dump` / `model_validate`

- Good: Pydantic is already a core dependency.
- Good: a typed session snapshot model can validate top-level fields and provide `model_dump_json` /
  `model_validate_json` for file serialization.
- Good: validation errors include useful field paths.
- Neutral: the dynamic `state` field remains `dict[str, Any]`, so custom nested state restoration still requires the
  framework registry.
- Neutral: the public `AgentSession` does not need to become a Pydantic model; an internal snapshot model can bridge it.
- Bad: benchmarked encode/decode includes model construction and dumping overhead on every operation.
- Bad: core dependency on Pydantic run the risk of us not being able to use different versions or users of the framework being unable to upgrade or having additional extra code dealing with major version bumps in Pydantic.

### msgspec typed/tagged unions only

- Good: msgspec owns validation and reconstruction end to end.
- Neutral: works well for a closed set of framework-owned `msgspec.Struct` types.
- Bad: every external type must be known when the decoder schema is constructed; dynamic registration is lost.

### msgspec codecs plus an explicit dynamic registry

- Good: one typed file encode/decode and dynamic nested custom types.
- Good: it satisfies the required readable JSON format.
- Neutral: the same typed snapshot can also support optional MessagePack as a low-cost implementation detail.
- Good: the registry can enforce stable IDs, codec completeness, and collision handling.
- Neutral: a single state-payload hook still recursively applies registry codecs.
- Bad: msgspec cannot infer dynamic types from JSON without the framework's type tags.

## Benchmark Evidence

A benchmark using a large `AgentSession` with 2,000 `Message` objects stored through
`InMemoryHistoryProvider`, nested standard dictionaries, registered custom classes, and registered Pydantic models
measured the complete `AgentSession.to_dict()` / codec / `AgentSession.from_dict()` path.

| Codec | File size | Encode median (ms) | Decode median (ms) | Round-trip median (ms) | Disk round-trip median (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Standard library JSON | 1.57 MiB | 33.503 | 14.316 | 55.261 | 75.226 |
| orjson | 1.57 MiB | 25.808 | 11.754 | 39.398 | 63.319 |
| Pydantic JSON | 1.57 MiB | 28.330 | 18.344 | 53.522 | 77.096 |
| msgspec JSON | 1.57 MiB | 26.019 | 11.379 | **38.060** | 62.230 |
| msgspec MessagePack | **1.45 MiB** | **25.134** | **11.201** | 38.512 | **58.112** |

The JSON encodings produced the same 1.57 MiB file size. msgspec JSON had the best median JSON round-trip latency,
slightly ahead of orjson, while also supporting typed top-level decoding. Pydantic validation added measurable decode
and disk-round-trip overhead without eliminating the dynamic state registry.

MessagePack reduced file size to 92.2% of JSON (about 7.8% smaller) and produced the best encode, decode, and disk
round-trip medians. Its in-memory round-trip median was effectively tied with msgspec JSON. This supports offering it
as a nice-to-have, but it is not required to justify choosing msgspec for JSON.

These results are workload- and machine-dependent, but they validate the architectural choice:

- use msgspec JSON as the readable default;
- optionally offer msgspec MessagePack when storage size or disk latency matters;
- retain the explicit registry for dynamic custom state in both formats;
- do not add orjson solely for a small JSON performance difference without typed decoding; and
- do not use Pydantic as the file codec when its validation overhead does not replace the registry.

## Decision Outcome

### Decision 1: Move the concrete overridable store to core

`SessionStore` moves to `agent-framework-core` as an experimental public API. It remains a concrete in-memory store and
the default used by `AgentState` in the `hosting` package. Its async `get`, `set`, and `delete` methods remain overridable for custom storage
implementations.

`FileSessionStore` subclasses `SessionStore` and provides durable atomic file persistence. No separate
`InMemorySessionStore`, protocol, or ABC is introduced. `agent-framework-hosting` consumes the core type and no longer
owns or re-exports `SessionStore` (this will be a breaking change in the `hosting` package).

Session-store keys use one restricted contract suitable for the built-in file implementation: at most 128 ASCII
letters, digits, `-`, and `_`. Logical `AgentSession.session_id` values outside a store are not globally constrained by
this file-oriented key contract.

### Decision 2: Use msgspec codecs plus an explicit dynamic registry

Chosen option: **msgspec codecs plus an explicit dynamic registry**.

`FileSessionStore` uses a typed internal `msgspec.Struct` snapshot with reusable JSON and MessagePack encoders/decoders.
JSON is the required and default format. Because msgspec can reuse the same typed snapshot and registry hooks,
`serialization_format="msgpack"` is also exposed as an optional compact binary convenience. The complete state
dictionary is wrapped in one custom field; its encode/decode hooks recursively translate explicitly registered types
to and from the existing tagged mappings in either format.

The dependency floor is `msgspec>=0.20.0` because core supports Python 3.14 and msgspec added Python 3.14 support in
version 0.20.0.

The public `AgentSession` remains a normal framework class. The msgspec Struct is an internal persistence DTO rather
than the inheritance base for runtime sessions. A targeted comparison against the dictionary-based msgspec path found
that the internal Struct improved JSON encode latency by about 9% and JSON round-trip latency by about 4%, without
changing file size.

`register_state_type` requires explicit registration, supports stable type IDs and optional codecs, rejects collisions,
and provides defaults for `to_dict` / `from_dict` classes and explicitly registered Pydantic models. Unknown persisted
type IDs remain raw dictionaries for compatibility.

`FileHistoryProvider` also adds msgspec JSON as its default JSON Lines codec. It supports the same explicit
`serialization_format="msgpack"` choice using length-prefixed append-only MessagePack records. Its existing `dumps` /
`loads` extension points remain temporarily for JSON compatibility, emit `DeprecationWarning` when supplied, and do
not apply to MessagePack. New code uses the built-in msgspec codecs.

## Follow-up Work

Audit the remaining file-backed stores to determine whether they benefit from the same typed msgspec treatment and
optional JSON / MessagePack formats. `FileCheckpointStorage` is the first candidate because it persists large,
structured workflow state and currently uses JSON plus custom checkpoint value encoding.

`MemoryContextProvider` is another candidate because its file-backed path combines `MemoryFileStore` state with
transcript files and still exposes `history_dumps` / `history_loads` passthroughs to the deprecated
`FileHistoryProvider` codec hooks.

The follow-up should measure real framework payloads before changing formats, preserve compatibility or define a clear
migration path for existing files, and consider whether each store needs readable JSON, compact binary storage, append
semantics, or atomic whole-file replacement. Other candidates include file-backed todo state, but each should be
evaluated independently rather than adopting msgspec by default solely for consistency.
