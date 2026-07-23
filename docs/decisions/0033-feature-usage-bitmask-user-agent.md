---
status: proposed
contact: eavanvalkenburg
date: 2026-07-22
deciders: eavanvalkenburg
consulted:
informed:
---

# Feature-usage bitmask in the User-Agent

## Context and Problem Statement

We can see which Agent Framework packages are installed and that *some* framework
call happened (via the existing `agent-framework-python/{version}` User-Agent),
but we have no usage-based signal about **which features are actually exercised**
at runtime, nor which are used *together* (e.g. workflows + MCP + Foundry). How
can we collect a lightweight, privacy-respecting signal of feature usage for the
traffic we can actually read, without standing up new event pipelines?

The detailed mechanism is in [SPEC-004](../specs/004-feature-usage-telemetry.md);
the per-language bit tables are in
[feature-usage-bit-registry.md](../specs/feature-usage-bit-registry.md).

## Decision Drivers

- **Transparency** — openly documented, human-decodable, user-controllable. No
  hidden or obfuscated telemetry.
- **First-party scope / no third-party leakage** — emission requires both an
  explicitly approved client/pipeline family and an approved actual HTTPS origin
  on every request (including redirects). Credentials or an Azure setting alone
  never approve a custom gateway/origin.
- **Live signal** — reflect features exercised *so far*, re-evaluated per request,
  not frozen at client construction.
- **Low cost / few moving parts** — reuse telemetry already in the request path;
  near-zero runtime overhead; as little machinery as the job needs.
- **Privacy** — encode only coarse boolean feature usage; no identifiers,
  arguments, prompts, payloads, model/deployment names, endpoints, or
  customer-defined names.
- **Use, not presence** — package-level indexes mean a capability reached its
  first meaningful activation, not that a package was installed/imported or a
  DI container constructed an unused service.
- **Versioning discipline** — v1 is a point-in-time decision. Adding bits later is
  easier than removing or redefining them, so the initial table should lean toward
  fewer bits and avoid forcing v2 shortly after launch.
- **Allocation discipline** — each bit represents a stable framework-owned
  capability with a concrete product/support question and an actual-use mark
  point; implementation detail and speculative distinctions stay out.

## Considered Options

The options below are grouped by the decisions that matter: the **transport**,
the **granularity**, and the **registry sharing model**.

### Transport

#### A. User-Agent token, first-party only, per request (chosen)

Stamp a `(feat=...)` comment onto the UA, but only on approved Azure/Foundry
client pipelines, and re-evaluate it per request.

- Good, reuses telemetry already sent to approved backends we can read.
- Good, per-request stamping reflects the live mask (not frozen at construction).
- Good, first-party scoping means no fingerprint leaks to third-party providers.
- Good, two-factor destination approval (pipeline + actual origin) denies custom
  `base_url` gateways and strips the token on unapproved redirect hops.
- Good, maps onto .NET's existing per-request UA pipeline policies unchanged.
- Neutral, v1 stamps only pipelines the framework creates or can configure
  through supported public hooks. It does not mutate caller-owned clients or
  reach into private SDK pipelines.
- Bad, no signal for traffic that never hits a first-party endpoint (accepted —
  we couldn't read it anyway).

#### B. User-Agent token on all clients

- Good, simplest to wire (one static header).
- Bad, sends a deployment fingerprint to OpenAI/Anthropic/AWS/Google logs we
  cannot read — privacy leak for zero benefit.
- Bad, baked into static `default_headers`, so it freezes at client construction
  and reports a near-empty mask.

#### C. OpenTelemetry span/resource attribute

- Good, precise per-call usage; no UA change.
- Bad (**privacy — the main reason to hold it**), a span attribute broadcasts the
  feature-combination fingerprint into the user's **general** telemetry pipeline,
  which is typically exported to third-party APM vendors (Datadog, Honeycomb, …).
  That re-introduces exactly the fingerprint leakage the first-party-only UA
  scoping (A) was chosen to avoid — just into a different set of third parties.
- Bad (secondary), also a cardinality footgun (a growing, combinatorial value
  must never become a metric dimension).
- Neutral, for the team's own goal it reaches us only if the user exports to
  Azure Monitor and we query it.
- **Deferred, not rejected.** The version prefix lets us add it later **if** the
  User-Agent path cannot answer a concrete query and there is an acceptable
  scoped/redacted variant.

#### D. Bespoke usage events

- Good, richest detail and flexibility.
- Bad, new data flow and cost; larger privacy surface; heavy to build and review;
  overkill for a coarse "which features" signal.

#### E. Install/import-time signal only (status quo-ish)

- Good, zero new runtime work.
- Bad, measures installation, not usage; cannot capture feature combinations —
  does not solve the problem.

### Accumulation scope

#### S1. Process-global, monotonic mask (chosen)

A single mask per process; bits are OR-ed in as features are first used and never
cleared. The token reflects "what this process has used so far."

- Good, fits our **mixed feature lifecycle**: many features are *not* bound to an
  outbound service request — an agent/workflow may first run or build, a
  context/history provider may first participate in a session, and a host may
  start serving before the request that later emits the token. A process-wide
  mask can carry those activations forward.
- Good, trivial and cheap: one OR under a lock (Python) / one atomic OR into one
  of two 64-bit lanes (.NET); no per-request state plumbing.
- Neutral, coarser than per-call — early requests carry fewer bits than later
  ones, and the token says "this process used X", not "this call used X".

#### S2. Per-request set, reset between calls (botocore's model — rejected)

AWS botocore scopes its `m/` feature codes to a `contextvars` set that is reset
between requests, giving exact per-call attribution (and it deliberately no-ops
when called outside a request context to avoid features bleeding across requests).
See [Prior art](#prior-art).

- Good, exact per-call attribution directly in the User-Agent.
- Bad, **assumes every feature is exercised inside a single service request** —
  true for botocore (an SDK natively bound to AWS service calls), but *not* for
  us. Our features split into request-scoped ones (a chat call, an MCP tool
  invocation) and decidedly non-request ones (workflow build/start, provider
  participation, hosting startup). The latter have no service request to attach to, so a
  per-request set would simply miss them.
- Bad, needs `contextvars` propagation through every async/threaded path and a
  reset discipline; the bleed-guard botocore documents is the warning sign.
- Note, per-call attribution for the request-scoped subset is better served by
  the deferred OTel span path (option C) than by reshaping the UA token.

### Granularity

The mechanism can support several granularities. The remaining decision before
implementation is how detailed v1 should be. The estimates below are
intentionally rough; v1 uses a fixed 128-bit bound to leave useful headroom
without making the registry unbounded.

#### F0. Package-level bits

One bit per package, set on first use of a package-owned public API, client,
provider, or tool. It is **not** set on install, import, or assembly load.

Examples that get bits:

- `agent-framework-core` when `Agent`, `AgentSession`, `Workflow`, etc. is used.
- `agent-framework-tools` when a `LocalShellTool` or `DockerShellTool` first
  executes/probes its shell capability.
- `agent-framework-foundry` when a `FoundryChatClient`, `FoundryAgent`, etc.
  performs its first Foundry operation.
- `agent-framework-openai` when `OpenAIChatClient`,
  `OpenAIEmbeddingClient`, etc. performs its first provider operation.
- `agent-framework-azure-ai-search` when `AzureAISearchContextProvider` is used.
- `agent-framework-azure-cosmos` when `CosmosHistoryProvider` is used.
- `agent-framework-redis` when `RedisContextProvider` or `RedisHistoryProvider`
  is used.

Examples that do **not** get separate bits: merely installed dependencies;
imports or DI construction with no activation; `Agent` vs `AgentSession` vs
`InMemoryHistoryProvider`; `FunctionTool` vs `MCPStdioTool` vs `LocalShellTool`
vs `DockerShellTool`; `FoundryChatClient` vs `FoundryAgent`; `OpenAIChatClient`
vs `OpenAIEmbeddingClient`.

Rough estimate: Python ~25-35 bits; .NET ~15-25 bits.

- Good, lowest specificity and simplest registry.
- Good, clearly measures usage rather than dependency inventory if bits are set
  only at package-owned public API/client/provider/tool use sites.
- Bad, does not answer which major capability within a package is used.

#### F1. Package + major capability bits

Package bits plus selected major capabilities that are product-distinct and stable
across implementations.

Examples that get bits:

- `agent-framework-core` plus `Agent`.
- `AgentSession` plus `InMemoryHistoryProvider` / `FileHistoryProvider` as one
  history capability.
- `Workflow` / `FunctionalWorkflow` as one workflow capability.
- `FunctionTool`; MCP transports as one MCP capability; shell tools as one shell
  capability.
- Skills provider plus stable source types: file, in-memory/programmatic, and
  MCP-backed skills (with .NET inline/class skill distinctions).
- Foundry chat/agent/embedding capabilities; OpenAI chat/embedding capabilities.

Examples that do **not** get separate bits: `InMemoryHistoryProvider` vs
`FileHistoryProvider`; `WorkflowBuilder`, `AgentExecutor`, `FunctionExecutor`, or
`FanOutEdgeGroup`; `MCPStdioTool` vs `MCPStreamableHTTPTool` vs
`MCPWebsocketTool`; `LocalShellTool` vs `DockerShellTool` vs
`ShellEnvironmentProvider` vs `ShellPolicy`; `OpenAIChatClient` vs
`OpenAIChatCompletionClient`; skill-source decorators such as caching, filtering,
deduplication, and aggregation.

Rough estimate: Python ~60-70 bits; .NET ~45-55 bits. The current candidate
registry is at 62 Python / 51 .NET assigned bits.

- Good, likely answers the first product adoption questions while staying compact.
- Good, fits comfortably within 128 bits while leaving room for additive package
  and feature growth.
- Neutral, some provider internals remain collapsed until a later additive bit is
  justified.

#### F2. Public construct / concrete type bits

One bit per public construct that users intentionally instantiate or configure.

Examples that get bits:

- `Agent`, `AgentSession`, `InMemoryHistoryProvider`, `FileHistoryProvider`.
- `Workflow`, `WorkflowBuilder`, `FunctionalWorkflow`.
- `FunctionTool`, `MCPStdioTool`, `MCPStreamableHTTPTool`, `MCPWebsocketTool`.
- `LocalShellTool`, `DockerShellTool`, `ShellEnvironmentProvider`, `ShellPolicy`.
- `FoundryChatClient`, `FoundryAgent`, `OpenAIChatClient`,
  `OpenAIChatCompletionClient`, `OpenAIEmbeddingClient`.

Examples that do **not** get separate bits: `Agent.run` vs
`Agent.run_streamed`; workflow edge/executor internals such as `AgentExecutor`,
`FunctionExecutor`, or `FanOutEdgeGroup`; `LocalShellTool` persistent vs
stateless mode; `ShellPolicy` allowlist vs denylist configuration; `FunctionTool`
approval mode or result parser choices.

Rough estimate: Python ~70-100 bits; .NET ~55-80 bits.

- Good, concrete and directly tied to public API use.
- Neutral, fits within 128 bits at the current estimate, but consumes much of the
  deliberate growth reserve.
- Bad, adds many call sites and more fingerprint specificity for v1.

#### F3. Construct subtype / configuration bits

Split important constructs by mode, transport, storage, or workflow primitive
when that distinction matters.

Examples that get bits:

- `InMemoryHistoryProvider` and `FileHistoryProvider` separately.
- `FunctionalWorkflow`, `WorkflowBuilder`, `AgentExecutor`, `FunctionExecutor`.
- `FanOutEdgeGroup`, `FanInEdgeGroup`, `SwitchCaseEdgeGroup`.
- `LocalShellTool` persistent, `LocalShellTool` stateless, `DockerShellTool`.
- `MCPStdioTool`, `MCPStreamableHTTPTool`, `MCPWebsocketTool`;
  `OpenAIChatClient` vs `OpenAIChatCompletionClient`.

Examples that do **not** get separate bits: exact session id or persisted history
file path; exact shell command, workdir, timeout, or output cap; exact MCP server
command, URL, or tool names from the server; exact workflow graph shape or edge
count; model/deployment names, prompts, tool arguments, payloads.

Rough estimate: Python ~110-150 bits; .NET ~85-125 bits.

- Good, useful where mode-level distinctions are decision-relevant.
- Bad, trades simplicity for precision, increases fingerprint specificity, and
  may exhaust or exceed 128 bits in Python.

#### F4. Option / behavior flag bits

The most detailed framework-owned option: bits for specific modes and behavior
switches, still excluding customer/runtime values.

Examples that get bits:

- Agent streaming used vs non-streaming used.
- `FunctionTool` `approval_mode="always_require"` vs `"never_require"`.
- `FunctionTool` `SKIP_PARSING` / result-parser path used.
- MCP sampling configured; MCP long-running task support used.
- `LocalShellTool` `clean_env` / `confine_workdir`; `DockerShellTool` container
  mode.

Examples that do **not** get separate bits: function names wrapped by
`FunctionTool`; approval rule arguments or approval decisions; MCP remote tool
names or schemas; shell command text or policy regex patterns; prompt/message
content, model names, URLs, tenant/user/session identifiers.

Rough estimate: Python 150+ bits; .NET 120+ bits.

- Good, maximum framework-owned detail.
- Bad, exceeds or nearly exhausts 128 bits and is too detailed for v1 without a
  concrete decision that requires it.

### Registry sharing model

#### H. Per-language bit lists (chosen)

Each SDK owns an independent list; the decoder picks the list using the language
already present in the UA product token.

- Good, **no cross-language coordination**: each SDK numbers and evolves its
  features independently; adding a Python feature never touches .NET numbering.
- Good, no null placeholders for one-SDK features, no "same bit, same meaning"
  rule, no SDK-aware decode caveats.
- Good, decoding is trivial: language (from UA) + version -> list -> AND.
- Neutral, two small lists to maintain instead of one (but they were going to
  diverge anyway — the packages differ).

#### I. Single shared cross-language registry

- Good, one list, one number space.
- Bad, forces synchronized numbering and null placeholders for features that
  exist in only one SDK, plus SDK-aware decode rules.
- Bad, the synchronization is pure accidental complexity — **the language is
  already in the User-Agent**, so sharing the number space buys nothing.

### Registry maintenance

#### J. Package-local indexes + parity/no-overlap test (chosen)

- Good, each package owns private `FeatureIndex` declarations only for its own
  rows; adding an optional-provider index does not require a core release after
  the marker API exists.
- Good, one repository test compares the package-local declarations with the
  per-language table and rejects missing rows, wrong ids, out-of-range indexes,
  and any duplicate/overlapping index.
- Good, no build step, no generator to own.

#### K. Code-generate the enums from the registry

- Bad, a generator + drift test + schema test to maintain a short list of
  integer constants; likely justified only if v1 deliberately chooses the most
  detailed L3/L4 granularities.

### Representation (how the mask is rendered as text)

All examples below encode the same mask — bits 0, 2, 32, 48, 56 set
(agent + workflow + sequential-orchestration + foundry.chat_client + openai, in
the Python v1 list) = decimal `72339073309605893`.

#### L. Decimal — `feat=v1.72339073309605893`

- Good, human-familiar; trivial to parse.
- Neutral, no visual alignment to bit/nibble boundaries; slightly longer than hex
  for large masks. No advantage over hex.

#### M. Hex (chosen) — `feat=v1.101000100000005`

- Good, compact (≤32 chars for a 128-bit mask).
- Good, decodes with one stdlib call in every language (`int(x, 16)` /
  two 64-bit lane parses in .NET); nibble boundaries are eyeball-able.
- Good, lowercase, no `0x` prefix, no leading zeros — unambiguous and stable.

#### N. Binary / bit-list — `feat=v1.100000001000000000000000100000000000000000000000000000101` or `feat=v1.0,2,32,48,56`

- Good, most directly human-readable ("which bits").
- Bad, longest form in the UA; the bit-list needs delimiter handling and grows
  with the number of set bits.

#### O. Alphabet / base-N (e.g. Crockford base32 `feat=v1.208004000005`, base62 `feat=v1.5LJRx1i6xJ`)

- Good, shortest representation.
- Bad, needs a custom alphabet + decode table on both ends; base62 is
  case-sensitive (fragile through case-normalizing intermediaries); not
  eyeball-able. Premature optimization for a value that is already ≤32 chars in
  hex.

## Decision Outcome

Chosen: **a per-request, first-party-only User-Agent `(feat=...)` token (A),
with a 128-bit process-global monotonic accumulator (S1), per-language bit lists
(H), package-local index enums kept honest by parity and no-overlap tests (J),
rendered as lowercase hex (M).**

This is a bounded design with enough v1 headroom. A 128-bit
**process-global, monotonic** mask accumulates from universal
`mark_feature_used()` calls (so it spans build/start/participation activations
that aren't bound to any service request — the per-request set model (S2) can't);
the token is **stamped per request** only when both the client/pipeline and the
actual HTTPS origin are approved, so custom origins and cross-origin redirects
cannot inherit the fingerprint; each
SDK owns an independent bit list selected by the language already in the UA; the
mask is rendered as hex (`feat=v1.101000100000005`). **Two opt-out env vars are
provided:** a dedicated `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED` that drops only
the mask while keeping the base SDK identity/version User-Agent, and the existing
`AGENT_FRAMEWORK_USER_AGENT_DISABLED` that drops the whole contribution. OTel (C)
is deferred — mainly because a broadly-emitted span attribute would leak the
fingerprint into the user's general telemetry, against the first-party-only
stance and would require user-side OTel setup that may still not make the data
available to us — but left open behind the version prefix. Per-request scoping
(S2), a shared registry (I), codegen for the initial registry (K), and the
decimal/binary/base-N representations (L, N, O) are rejected as complexity or
length the problem does not require.

The remaining choice before implementation is the **v1 granularity level** among
F0-F4. This is a point-in-time decision: adding new bits later is easier than
removing or redefining them, because removals/redefinitions require a new
registry version and historical decode tables. For v1, prefer the least detailed
level that answers the known product/support questions so we do not force a v2
shortly after launch. The refreshed candidate registry uses **62 Python bits and
51 .NET bits**, leaving 66 and 77 positions respectively. That headroom supports
normal growth; it does not waive the registry's
[allocation tenet](../specs/feature-usage-bit-registry.md#allocation-tenet).

### Consequences

- Good, adds usage signal at near-zero cost, no new data flow, few moving parts.
- Good, transparent (public registry, human-decodable token) and disabled by
  **two** opt-out env vars: a dedicated `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED`
  (mask only) and `AGENT_FRAMEWORK_USER_AGENT_DISABLED` (whole UA; existing in
  Python and added to .NET with this work).
- Good, first-party-only + per-request emission gives a live mask and no
  third-party fingerprint leak.
- Good, 128 bits leaves useful v1 headroom; .NET remains lock-free by storing two
  independently atomic 64-bit lanes; per-language lists remove all cross-language
  sync; package-local enums avoid both codegen and provider→core release coupling.
- Neutral, the token's reach equals eligible framework-configured first-party
  traffic; broader per-call signal (OTel) can be added later if needed.
- Neutral, v1 granularity is intentionally a separate choice; the registry should
  start with fewer bits unless a more detailed bit answers a concrete question.
- Bad, each feature must add an activation mark, first-party clients need a
  per-request destination-aware hook, and the registry validator must scan all
  package-local index declarations.

## Prior art

SDK telemetry-in-the-User-Agent is well-established; this design is closest to
AWS's, and conventional in the rest. Summary of what comparable SDKs do:

| SDK | What's in the UA / headers | Usage-based? | Opt-out | Closest to ours? |
| --- | --- | --- | --- | --- |
| **AWS botocore** | structured UA with an `m/` token: a per-request set of **short feature codes** for features actually exercised (`WAITER`→`B`, `PAGINATOR`→`C`, retry mode, checksums, credential source, …) | **Yes** — registered at call time via `register_feature_id`, contextvar-scoped per request | `AWS_SDK_UA_APP_ID` sets app id (no opt-out for `m/`) | **Yes — direct analog** |
| **OpenAI / Anthropic** (Stainless) | sidecar `X-Stainless-*` headers: lang, package version, OS, arch, runtime, runtime version; plus per-request `x-stainless-retry-count`, `x-stainless-read-timeout` | Mostly static identity (retry/timeout are per-request) | none | No (static identity) |
| **Azure SDK** (`azure-core`) | `User-Agent: azsdk-python-{pkg}/{ver} Python/{pyver} ({platform})` | No | `AZURE_TELEMETRY_DISABLED` (tracing spans only, **not** the UA) | No |
| **Google API core** | `x-goog-api-client: gl-python/… grpc/… gax/… gapic/…` | No | none | No |
| **LangSmith** | `User-Agent: langsmith-py/{ver}`; usage lives in trace payloads | No (header) | opt-in via `LANGSMITH_TRACING_V2`/`LANGCHAIN_TRACING_V2`; `…HIDE_INPUTS/OUTPUTS` | No |

Takeaways that shaped (or validate) our choices:

- **AWS `m/` is the precedent for usage-based feature flags in a first-party
  User-Agent.** It validates the core idea. Its key *difference* is the encoding:
  AWS uses a **comma-separated set of 1–2 char short codes** (open-ended, no bit
  coordination, but variable length), whereas we use a fixed-width **hex
  bitmask** (compact, bounded, decode-by-AND, but needs per-language bit
  allocation). We keep the bitmask for boundedness and trivial AND-decoding;
  AWS's short-code set is recorded as a viable alternative if bit-position
  coordination ever becomes painful (it would also drop the fixed 128-bit bound).
- **A fixed-width bitmask gives bounded token size for free.** botocore must cap
  the `m/` component at 1024 bytes and truncate at delimiter boundaries (with a
  fallback log) precisely *because* its short-code set is unbounded. Our 128-bit
  hex is ≤32 chars by construction — no size cap, no truncation logic.
- **Scope is where we diverge most — and deliberately.** botocore collects
  features into a per-request `contextvars` set that is **reset between
  requests**, and no-ops outside a request context to prevent cross-request
  bleed. That works because every botocore feature is exercised *inside* an AWS
  service request. We are more general: some features are request-scoped (a chat
  call, an MCP tool invocation) but many are **not bound to any request**
  (workflow build/start, provider participation, hosting startup). So we use a
  **process-global, monotonic** mask (option S1), which is the only scope that can
  represent the non-request features. Our mask therefore intentionally "bleeds"
  (accumulates) for the life of the process — the opposite of botocore's reset —
  and that is the intended semantic, not the bug botocore guards against.
- **The mechanism is private; the wire format is the contract.** botocore marks
  its whole user-agent module private and "subject to abrupt breaking changes."
  Same for us: the Python/.NET helpers are internal, and only the emitted token +
  the per-language registry tables are the stable, decodable contract.
- **First-party-only emission** is stricter than any of the above; the closest in
  spirit is Stainless headers, which only reach the owning API. We make the
  client/pipeline allowlist explicit (initially Foundry/Azure OpenAI) rather than
  attempting to infer safety from arbitrary request URLs. Other Azure clients
  join only after telemetry access is confirmed.
- **Opt-out naming.** `AZURE_TELEMETRY_DISABLED` is the family precedent for our
  `AGENT_FRAMEWORK_*_DISABLED` names. Separately, the cross-tool `DO_NOT_TRACK`
  convention (honored by e.g. HuggingFace Hub) is worth considering — see Open
  Questions.

Sources: botocore [`useragent.py`](https://github.com/boto/botocore/blob/develop/botocore/useragent.py)
(`_USERAGENT_FEATURE_MAPPINGS`, `register_feature_id`, `_build_feature_metadata`);
openai-python [`_base_client.py` `platform_headers()`](https://github.com/openai/openai-python/blob/main/src/openai/_base_client.py);
anthropic-sdk-python [`_base_client.py`](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/_base_client.py);
azure-core [`_universal.py` `UserAgentPolicy`](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/core/azure-core/azure/core/pipeline/policies/_universal.py);
google-api-core [`client_info.py`](https://github.com/googleapis/python-api-core/blob/main/google/api_core/client_info.py);
langsmith-sdk [`client.py`](https://github.com/langchain-ai/langsmith-sdk/blob/main/python/langsmith/client.py) /
[`utils.py`](https://github.com/langchain-ai/langsmith-sdk/blob/main/python/langsmith/utils.py);
huggingface_hub [`constants.py`](https://github.com/huggingface/huggingface_hub/blob/main/src/huggingface_hub/constants.py).

## Registry versioning and migration (v1 → v2)

The token carries a **per-language** version (`feat=v1.<hex>`); a version bump is
independent for Python and .NET.

- **Additive growth stays on v1 — no bump.** Allocating a new feature to a
  reserved/unused bit is backward-compatible: an older decoder simply sees an
  unknown bit and ignores it. Normal package growth never needs a new
  version.
- **A bump (v2) is required only for breaking changes:** renumbering or
  re-partitioning existing bits, changing the *meaning* of an already-assigned
  index, or widening beyond 128-bit. Within a version an index is **never** reused or
  reassigned — that invariant is what lets old decoders stay correct.
- **The draft 64→128 change is still v1.** No v1 token or enum has shipped, so
  this pre-implementation repartition establishes the initial contract rather
  than migrating an existing one.
- **Mixed-version coexistence is the norm.** A fleet runs many SDK releases at
  once, so `v1` and `v2` tokens appear simultaneously for a long time (old SDKs
  keep emitting `v1`). The decoder keeps **every** published `(language,
  version)` table and selects by the token's version; the `v1` table is retained
  indefinitely for historical decode.
- **Unknown version → do not guess.** A decoder without the `vN` table must
  record "unknown registry version" rather than decode against an older table —
  bit meanings may differ across versions, so mis-attribution is worse than
  no data.
- **Producing v2:** publish the v2 table alongside v1, update the affected
  package-local `FeatureIndex` declarations and SDK version constant, and emit
  `v2` from the release that ships them. Prefer staying on v1 (additive) and
  reserving a clean v2 for an eventual deliberate re-partition.

## Limitations

| Limitation | Caused by (choice) | Why we accepted it |
| --- | --- | --- |
| **No signal for self-hosted or third-party-only traffic.** If a process never calls Azure/Foundry, we see nothing. | First-party-only emission (A) | We can't read third-party logs anyway, and must not leak a fingerprint into them. Reach traded for privacy. |
| **Not every first-party client is stampable.** Caller-supplied `AIProjectClient` / OpenAI clients and toolkit-owned clients may not expose a supported per-request policy hook. | Supported-hook-only emission (A) | V1 does not mutate caller-owned clients or private SDK pipelines. Those features may still appear on another eligible request from the same process-global mask. |
| **Custom origins intentionally receive no feature token.** A customer gateway may use Azure credentials or Azure-named settings but route to a non-approved origin. | Two-factor destination classification (A) | Credentials and configuration names are not proof of telemetry ownership. Unknown/custom origins and cross-origin redirects are denied by default. |
| **No OTel / per-call signal in v1.** | OTel deferred (C) — primarily on **privacy** and availability grounds | A broadly-emitted span attribute would push the fingerprint into the user's general telemetry / third-party APM vendors, undoing the first-party-only scoping. It also requires customer/user OTel setup, and even Foundry users may not export data where we can query it. Left open only if there is a compelling reason to add. |
| **Mask reflects "usage so far," not the whole session.** Early requests carry fewer bits than later ones. | Process-global accumulator + per-request stamping | Honest and still useful; the team aggregates across requests. The per-request design is what makes it *grow* rather than freeze. |
| **No per-agent / per-call attribution.** The mask is one process-wide value — "this process used X", not "this agent/call used X". | Process-global monotonic scope (S1) | A deliberate choice, not a transport limit: botocore *does* per-call attribution in the UA via a per-request `contextvars` set, but many AF activations (workflow build/start, provider participation, hosting startup) occur outside the service request that later emits the token. Per-call detail remains deferred to OTel. |
| **Shared processes intentionally carry usage across agents and tenants.** A request can include bits first set by another workload in the same worker. | Process-global monotonic scope (S1) | The token must be interpreted only as process-level "used so far," never as request/user/tenant attribution. Privacy review must explicitly accept this. |
| **Counts are request-weighted and sticky.** Once set, a bit appears on every later eligible request from that process, so long-lived/high-traffic processes dominate. | Monotonic mask emitted per request | The signal supports traffic prevalence and co-occurrence, not first-use counts, unique-process counts, or exact feature invocation frequency. |
| **Granularity may be too coarse or too detailed.** The chosen level may miss useful distinctions or create more specificity than needed. | v1 granularity choice (F0-F4) | This is the main remaining decision. Adding bits later is easier than removing/redefining them, so v1 should lean toward fewer bits that answer known questions. |
| **.NET snapshots span two atomic lanes.** A bit can be marked between the low/high reads, so one request may omit that just-added bit. | 128-bit width without a global lock | The mask is monotonic: the snapshot cannot invent or clear a bit, and the next request includes the addition. This matches the existing "usage so far" timing semantics. |
| **Fingerprinting risk is reduced, not eliminated.** A feature-combination mask is still a deployment signature, and it transits intermediaries (proxies/CDNs) even when first-party-scoped. | Emitting any feature-combination value | Scope + opt-out + coarse granularity mitigate it; v1 should avoid unnecessary detailed bits. |

## Open Questions (for decider discussion)

These are unresolved and should be decided before implementation:

1. **Which v1 granularity level (F0-F4)?** This is the primary remaining choice.
   Adding bits later is easier than removing or redefining bits, so v1 should
   choose the least detailed level that answers known questions and avoids a quick
   v2.
2. **Privacy approval for the v1 User-Agent signal.** Before implementation,
   confirm that a transparent, opt-out, first-party-only feature-combination
   fingerprint is acceptable, including the exact client allowlist, retention,
   access, and permitted product queries. This is a rollout precondition.
3. **When (if ever) to add the OTel path?** Held back mainly for **privacy** and
   data availability: a span attribute broadcasts the fingerprint into the user's
   general telemetry and onward to third-party APM vendors, contradicting the
   first-party-only stance, and it requires user-side OTel setup that may not make
   the data available to us even for Foundry users. It also carries a
   metric-cardinality hazard. Revisit only if the User-Agent path cannot answer a
   concrete question.
4. **Honor the cross-tool `DO_NOT_TRACK` convention?** Several ecosystems treat
   `DO_NOT_TRACK=1` as a universal telemetry opt-out (HuggingFace Hub honors it;
   see [Prior art](#prior-art)). Should our opt-out also respect `DO_NOT_TRACK`
   (in addition to the two `AGENT_FRAMEWORK_*` flags)? Cheap to add and
   community-friendly, but it widens the opt-out surface and needs a clear
   precedence rule. Recommend yes; confirm with the deciders.

### Decided

- **Dedicated opt-out flag — included.** In addition to the existing
  Python `AGENT_FRAMEWORK_USER_AGENT_DISABLED` (drops the whole UA), v1 ships
  `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED`, which drops **only** the feature mask
  while keeping the base SDK identity/version User-Agent. This lets a
  privacy-conscious user withhold the usage signal without losing the
  support/compat value of the SDK-version header. .NET adopts both environment
  variable names when it adds the feature.
- **Caller-owned clients are not modified.** V1 stamps only framework-created
  clients or clients with a supported public policy/hook registration point. It
  does not patch private pipelines; injected clients are an explicit coverage
  limitation.
- **Destination approval is explicit and redirect-aware.** An eligible pipeline
  still emits only to a reviewed HTTPS origin. Custom origins are default-deny,
  and the token is removed on an unapproved redirect hop.
- **Marking uses activation, not DI construction.** Operational surfaces mark on
  first real use; a constructor marks only when construction itself exercises or
  registers the capability.

## More Information

- Mechanism & API: [SPEC-004](../specs/004-feature-usage-telemetry.md)
- Per-language bit tables, encoding, opt-out, governance: [feature-usage-bit-registry.md](../specs/feature-usage-bit-registry.md)
- Existing accumulator pattern: `python/packages/core/agent_framework/_telemetry.py`
- .NET emission policies: `dotnet/src/Microsoft.Agents.AI.Foundry/AgentFrameworkUserAgentPolicy.cs`,
  `dotnet/src/Microsoft.Agents.AI.Foundry.Hosting/HostedAgentUserAgentPolicy.cs`
