---
status: proposed
contact: eavanvalkenburg
date: 2026-06-12
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

The detailed mechanism is in [SPEC-002](../specs/002-feature-usage-telemetry.md);
the per-language bit tables are in
[feature-usage-bit-registry.md](../specs/feature-usage-bit-registry.md).

## Decision Drivers

- **Transparency** — openly documented, human-decodable, user-controllable. No
  hidden or obfuscated telemetry.
- **First-party scope / no third-party leakage** — emit only to Azure/Foundry
  endpoints (the telemetry we can ingest); never leak a feature fingerprint into
  third-party logs we cannot read.
- **Live signal** — reflect features exercised *so far*, re-evaluated per request,
  not frozen at client construction.
- **Low cost / few moving parts** — reuse telemetry already in the request path;
  near-zero runtime overhead; as little machinery as the job needs.
- **Privacy** — encode only coarse boolean feature usage; no identifiers,
  arguments, prompts, or payloads.

## Considered Options

The options below are grouped by the decisions that matter: the **transport**,
the **granularity**, and the **registry sharing model**.

### Transport

#### A. User-Agent token, first-party only, per request (chosen)

Stamp a `(feat=...)` comment onto the UA, but only on Azure/Foundry clients, and
re-evaluate it per request.

- Good, reuses telemetry already sent to the one backend we can read.
- Good, per-request stamping reflects the live mask (not frozen at construction).
- Good, first-party scoping means no fingerprint leaks to third-party providers.
- Good, maps onto .NET's existing per-request UA pipeline policies unchanged.
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
  privacy review blesses a broadly-emitted mask (or a scoped/redacted variant)
  and a concrete query needs the per-call precision.

#### D. Bespoke usage events

- Good, richest detail and flexibility.
- Bad, new data flow and cost; larger privacy surface; heavy to build and review;
  overkill for a coarse "which features" signal.

#### E. Install/import-time signal only (status quo-ish)

- Good, zero new runtime work.
- Bad, measures installation, not usage; cannot capture feature combinations —
  does not solve the problem.

### Granularity

#### F. Per package, with core broken out per feature/provider (chosen)

- Good, ~50 bits (Python) / ~40 (.NET) fit a **64-bit** mask, which keeps .NET's
  accumulator lock-free (`Interlocked.Or`) and the registry hand-maintainable.
- Good, matches the actual questions ("which orchestration / which built-in
  provider / which package?") — each orchestration pattern and each built-in
  context/history provider gets its own bit, since they serve different purposes.
- Neutral, cannot distinguish sub-features *within* a provider package (e.g.
  openai chat vs embeddings) until a bit is promoted.

#### G. Per construct (one bit per instantiable type)

- Good, finest detail.
- Bad, ~96 bits forces a 128-bit mask, which forfeits .NET's lock-free
  `Interlocked.Or` (needs a lock / `UInt128`).
- Bad, ~96 call sites across two SDKs; the sheer count pushes toward code
  generation and extra tests — machinery to manage machinery.
- Bad, precision nobody's decision actually needs.

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

#### J. Hand-written enum + parity test (chosen)

- Good, ~40 members that change a few times a year; a 10-line test (the enum vs
  the per-language table in the registry doc) is enough.
- Good, no build step, no generator to own.

#### K. Code-generate the enums from the registry

- Bad, a generator + drift test + schema test to maintain a short list of
  integer constants; justified only by the per-construct bit count we rejected.

### Representation (how the mask is rendered as text)

All examples below encode the same mask — bits 0, 2, 16, 22, 27 set
(agent + workflow + sequential-orchestration + foundry.chat_client + openai, in
the Python v1 list) = decimal `138477573`.

#### L. Decimal — `feat=v1.138477573`

- Good, human-familiar; trivial to parse.
- Neutral, no visual alignment to bit/nibble boundaries; slightly longer than hex
  for large masks. No advantage over hex.

#### M. Hex (chosen) — `feat=v1.8410005`

- Good, compact (≤16 chars for a 64-bit mask).
- Good, decodes with one stdlib call in every language (`int(x, 16)` /
  `Convert.ToUInt64(x, 16)`); nibble boundaries are eyeball-able.
- Good, lowercase, no `0x` prefix, no leading zeros — unambiguous and stable.

#### N. Binary / bit-list — `feat=v1.1000010000010000000000000101` or `feat=v1.0,2,16,22,27`

- Good, most directly human-readable ("which bits").
- Bad, longest form in the UA; the bit-list needs delimiter handling and grows
  with the number of set bits.

#### O. Alphabet / base-N (e.g. Crockford base32 `feat=v1.442005`, base62 `feat=v1.9n2lf`)

- Good, shortest representation.
- Bad, needs a custom alphabet + decode table on both ends; base62 is
  case-sensitive (fragile through case-normalizing intermediaries); not
  eyeball-able. Premature optimization for a value that is already ≤16 chars in
  hex.

## Decision Outcome

Chosen: **a per-request, first-party-only User-Agent `(feat=...)` token (A),
with per-package granularity (F), per-language bit lists (H), hand-written enums
kept honest by a parity test (J), rendered as lowercase hex (M).**

This is the smallest design that answers the question. A 64-bit mask accumulates
from universal `mark_feature_used()` calls; the token is stamped per request only
on Azure/Foundry clients (live, no third-party leak); each SDK owns an
independent bit list selected by the language already in the UA; the mask is
rendered as hex (`feat=v1.8410005`). **Two opt-out env vars are provided:** a
dedicated `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED` that drops only the mask while
keeping the base SDK identity/version User-Agent, and the existing
`AGENT_FRAMEWORK_USER_AGENT_DISABLED` that drops the whole contribution. OTel (C)
is deferred — mainly because a broadly-emitted span attribute would leak the
fingerprint into the user's general telemetry, against the first-party-only
stance — but left open behind the version prefix. Per-construct granularity (G),
a shared registry (I), codegen (K), and the decimal/binary/base-N representations
(L, N, O) are rejected as complexity or length the problem does not require.

### Consequences

- Good, adds usage signal at near-zero cost, no new data flow, few moving parts.
- Good, transparent (public registry, human-decodable token) and disabled by
  **two** opt-out env vars: a dedicated `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED`
  (mask only) and the existing `AGENT_FRAMEWORK_USER_AGENT_DISABLED` (whole UA).
- Good, first-party-only + per-request emission gives a live mask and no
  third-party fingerprint leak.
- Good, 64-bit keeps .NET lock-free; per-language lists remove all cross-language
  sync; hand-written enums avoid a codegen toolchain.
- Neutral, the token's reach equals first-party traffic; broader per-call signal
  (OTel) can be added later if needed.
- Bad, each feature must add a `mark_feature_used()` call, and first-party clients
  need a per-request hook (small, mirrors existing patterns).

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
  coordination ever becomes painful (it would also drop the 64-bit ceiling).
- **First-party-only emission** is stricter than any of the above; the closest in
  spirit is Stainless headers, which only reach the owning API. We make the
  hostname/endpoint allowlist explicit (Azure/Foundry only).
- **Opt-out naming.** `AZURE_TELEMETRY_DISABLED` is the family precedent for our
  `AGENT_FRAMEWORK_*_DISABLED` names. Separately, the cross-tool
  the cross-tool `DO_NOT_TRACK` convention (honored by e.g.
  HuggingFace Hub) is worth considering — see Open Questions.

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
  unknown high bit and ignores it. Normal package growth never needs a new
  version.
- **A bump (v2) is required only for breaking changes:** renumbering or
  re-partitioning existing bits, changing the *meaning* of an already-assigned
  bit, or widening beyond 64-bit. Within a version a bit is **never** reused or
  reassigned — that invariant is what lets old decoders stay correct.
- **Mixed-version coexistence is the norm.** A fleet runs many SDK releases at
  once, so `v1` and `v2` tokens appear simultaneously for a long time (old SDKs
  keep emitting `v1`). The decoder keeps **every** published `(language,
  version)` table and selects by the token's version; the `v1` table is retained
  indefinitely for historical decode.
- **Unknown version → do not guess.** A decoder without the `vN` table must
  record "unknown registry version" rather than decode against an older table —
  bit meanings may differ across versions, so mis-attribution is worse than
  no data.
- **Producing v2:** publish the v2 table alongside v1 in the registry doc, bump
  that SDK's `FeatureBit` enum + version constant; the SDK emits `v2` from the
  release it ships in. Prefer staying on v1 (additive) and reserving a clean v2
  for an eventual deliberate re-partition.

## Limitations

| Limitation | Caused by (choice) | Why we accepted it |
| --- | --- | --- |
| **No signal for self-hosted or third-party-only traffic.** If a process never calls Azure/Foundry, we see nothing. | First-party-only emission (A) | We can't read third-party logs anyway, and must not leak a fingerprint into them. Reach traded for privacy. |
| **No OTel / per-call signal in v1.** | OTel deferred (C) — primarily on **privacy** grounds | A broadly-emitted span attribute would push the fingerprint into the user's general telemetry / third-party APM vendors, undoing the first-party-only scoping. Left open to add later if there is a compelling reason to add. |
| **Mask reflects "usage so far," not the whole session.** Early requests carry fewer bits than later ones. | Process-global accumulator + per-request stamping | Honest and still useful; the team aggregates across requests. The per-request design is what makes it *grow* rather than freeze. |
| **No per-agent / per-call attribution.** The mask is one process-wide value — "this process used X", not "this agent/call used X". | Single global accumulator (simplicity) | Per-call attribution is what the deferred OTel span path would add; not needed for portfolio-level questions. |
| **Coarse granularity.** Can't distinguish sub-features (e.g. openai chat vs embeddings, which shell tool). | Per-package granularity (F) + 64-bit (keeps .NET lock-free) | Matches the actual questions; finer bits can be promoted later behind the version prefix. |
| **Fingerprinting risk is reduced, not eliminated.** A feature-combination mask is still a deployment signature, and it transits intermediaries (proxies/CDNs) even when first-party-scoped. | Emitting any feature-combination value | Scope + opt-out + coarse granularity mitigate it; residual risk is the subject of the privacy review below. |

## Open Questions (for decider discussion)

These are unresolved and should be decided before/at approval:

1. **Privacy / telemetry-acceptance review (blocking).** Is a coarse,
   first-party-only, opt-out-able feature-combination mask acceptable telemetry?
   Even scoped, it transits intermediaries and is a deployment fingerprint. This
   is a **release precondition**. Possible outcomes that would further change the
   design: coarser granularity, hashing, or explicit opt-in (a dedicated mask-only
   opt-out flag is already included — see below).
2. **When (if ever) to add the OTel path?** Held back mainly for **privacy**: a
   span attribute broadcasts the fingerprint into the user's general telemetry
   and onward to third-party APM vendors, contradicting the first-party-only
   stance. It also carries a metric-cardinality hazard. Would the privacy review
   allow a broadly-emitted mask, a scoped/redacted variant, or none? Decide if/when
   to revisit.
3. **Honor the cross-tool `DO_NOT_TRACK` convention?** Several ecosystems treat
   `DO_NOT_TRACK=1` as a universal telemetry opt-out (HuggingFace Hub honors it;
   see [Prior art](#prior-art)). Should our opt-out also respect `DO_NOT_TRACK`
   (in addition to the two `AGENT_FRAMEWORK_*` flags)? Cheap to add and
   community-friendly, but it widens the opt-out surface and needs a clear
   precedence rule. Recommend yes; confirm with the deciders.

### Decided

- **Dedicated opt-out flag — included.** In addition to the existing
  `AGENT_FRAMEWORK_USER_AGENT_DISABLED` (drops the whole UA), v1 ships
  `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED`, which drops **only** the feature mask
  while keeping the base SDK identity/version User-Agent. This lets a
  privacy-conscious user withhold the usage signal without losing the
  support/compat value of the SDK-version header.

## More Information

- Mechanism & API: [SPEC-002](../specs/002-feature-usage-telemetry.md)
- Per-language bit tables, encoding, opt-out, governance: [feature-usage-bit-registry.md](../specs/feature-usage-bit-registry.md)
- Existing accumulator pattern: `python/packages/core/agent_framework/_telemetry.py`
- .NET emission policies: `dotnet/src/Microsoft.Agents.AI.Foundry/AgentFrameworkUserAgentPolicy.cs`,
  `dotnet/src/Microsoft.Agents.AI.Foundry.Hosting/HostedAgentUserAgentPolicy.cs`
