---
status: proposed
contact: eavanvalkenburg
date: 2026-07-22
deciders: eavanvalkenburg
consulted:
informed:
---

# Feature-usage telemetry via an accumulating bitmask

> Companion design for [ADR-0033](../decisions/0033-feature-usage-bitmask-user-agent.md).
> The per-language bit tables, encoding, opt-out, and governance live in
> [feature-usage-bit-registry.md](feature-usage-bit-registry.md). The registry
> allocates indexes; package-local `FeatureIndex` declarations implement them.

## What is the goal of this feature?

Give the Agent Framework team a lightweight signal about **which framework
features are actually exercised** at runtime (not merely installed), so we can
prioritise investment based on real usage. We emit a single small number — a
*feature mask* — on the User-Agent that already goes out with each request.

**Reach is deliberately bounded.** The mask accumulates from *all* feature usage,
but the `feat=` token is only stamped through an explicit allowlist of
**first-party Azure/Foundry client pipelines** whose User-Agent telemetry the
team can ingest (initially Foundry/Azure OpenAI). We do **not** send the token to
third-party providers (OpenAI direct, Anthropic, Bedrock, Gemini, Ollama,
Mistral), or to an Azure service merely because its hostname is first-party;
doing so would leak a deployment fingerprint into logs we cannot read (see
[Emission](#emission)).

The current candidate uses package-level bits plus selected major capabilities:
one bit per orchestration pattern (sequential / concurrent / group-chat /
magentic / handoff), **one bit per built-in context/history provider**, selected
skill source types, and separate Foundry chat/agent/memory/evals/toolbox bits
(plus embedding in Python).
See the
[registry](feature-usage-bit-registry.md). ADR-0033 still leaves final v1
granularity open. The refreshed candidate assigns 62 Python bits and 51 .NET
bits. V1 uses 128 bits, leaving 66 Python and 77 .NET positions for additive
growth.

Success metric: within one release after rollout, ≥80% of **eligible,
framework-created** first-party (Foundry) requests carry a **non-empty** feature
token whose mask reflects features activated **after** client construction (i.e.
the token is live, not frozen — see the per-request requirement below).
Secondary: ability to break down first-party traffic by feature combination
(e.g. "% of Foundry traffic that also uses workflows").

This is done **transparently**: the bit registry is public, the emitted value is
human-decodable, and two env vars disable it — a dedicated
`AGENT_FRAMEWORK_FEATURE_MASK_DISABLED` (mask only) and the existing
`AGENT_FRAMEWORK_USER_AGENT_DISABLED` (whole User-Agent).

## What is the problem being solved?

Today we only know which packages are *installed* (from package telemetry) or
that *some* Agent Framework call happened (the existing
`agent-framework-python/{version}` User-Agent). We have no usage-based signal
about feature combinations, and no way to tell that, say, a process uses
workflows + MCP + Foundry together. Collecting this through bespoke events would
add cost and new data flows; folding a tiny accumulating integer into telemetry
we already send is far cheaper and easier to reason about for privacy.

## Mechanism

### Process-global accumulator in `core`

The accumulator and its helpers live in the existing
`agent_framework/_telemetry.py` (alongside `get_user_agent()` /
`prepend_agent_framework_to_user_agent()`), so the User-Agent machinery stays in
one module. It owns a process-global 128-bit accumulator. Python's arbitrary-size
`int` stores it directly. Two env vars can disable
it: the existing Python `AGENT_FRAMEWORK_USER_AGENT_DISABLED` (which drops the
whole User-Agent contribution, mask included), and a **dedicated**
`AGENT_FRAMEWORK_FEATURE_MASK_DISABLED` that drops **only** the feature mask while
keeping the base `agent-framework-python/{version}` User-Agent:

```python
# agent_framework/_telemetry.py (same module as get_user_agent)
# IS_TELEMETRY_ENABLED already defined here (AGENT_FRAMEWORK_USER_AGENT_DISABLED)

FEATURE_MASK_DISABLED_ENV_VAR = "AGENT_FRAMEWORK_FEATURE_MASK_DISABLED"
REGISTRY_VERSION = 1

_feature_mask = 0
_feature_mask_lock = threading.Lock()


def _feature_mask_enabled() -> bool:
    """Mask is on unless the UA is disabled or the dedicated flag is set."""
    if not IS_TELEMETRY_ENABLED:
        return False
    return os.environ.get(FEATURE_MASK_DISABLED_ENV_VAR, "false").lower() not in ("true", "1")


def mark_feature_used(index: int) -> None:
    """OR a feature bit into the process-global mask.

    Called the first time a feature is exercised. Cheap and idempotent;
    a no-op when the feature mask is disabled.
    """
    global _feature_mask
    if not _feature_mask_enabled():
        return
    if not 0 <= index < 128:
        raise ValueError(f"Feature index must be in range 0..127, got {index}")
    with _feature_mask_lock:
        _feature_mask |= 1 << index


def get_feature_token() -> str | None:
    """Return ``v<version>.<hex_mask>`` for the accumulated mask, or None."""
    if not _feature_mask_enabled() or _feature_mask == 0:
        return None
    return f"v{REGISTRY_VERSION}.{_feature_mask:x}"
```

- **Per package/feature, usage-based:** `mark_feature_used()` is called at the
  feature's first meaningful activation, never at import/install time. For
  operational clients, tools, providers, and hosts, activation is the first
  public operation that exercises the capability. Construction is a valid mark
  point only when construction itself performs the capability (for example,
  registering/starting runtime resources), not merely because a DI container
  instantiated an otherwise-unused object.
- **Process-global and monotonic — intentionally never reset.** Unlike a
  per-request scheme (e.g. botocore's `contextvars` feature set that resets
  between calls), our mask spans the whole process because many features are not
  bound to any service request — an agent or workflow may first run, a provider
  may first participate in a session, and a host may start serving independently
  of the later request that emits the token. The single global
  mask is the only scope that can represent them, and its monotonic "usage so
  far" growth is the intended semantic, not a bleed bug. Concurrency-safe via the
  module lock (Python) / two atomic 64-bit lanes in .NET.
- **Token is safe by construction.** The emitted value is `v{int}.{hex}` —
  characters limited to `[0-9a-fv.]` — so no header-injection sanitization is
  required. A 128-bit mask is at most 32 hex characters (contrast botocore,
  which must sanitize and cap arbitrary component strings).
- **Private API.** `mark_feature_used`, `get_feature_token`, `apply_feature_token`
  and the mask itself are internal helpers; only the emitted token and the
  per-language registry tables are the stable, decodable contract.
- **No import cycles:** the accumulator lives in core, while each package owns
  private index constants for its own features and calls the core marker. Core
  never imports optional packages.

### Bit constants

The registry is the allocation authority. Each package defines a private,
hand-written `FeatureIndex` IntEnum (or equivalent constants) containing only
the rows it owns. Core owns core indexes plus the accumulator; optional packages
can allocate and ship new indexes without requiring a core release after the
marker API exists.

```python
# agent_framework_foundry/_feature_usage.py
from enum import IntEnum

from agent_framework._telemetry import mark_feature_used  # pyright: ignore[reportAttributeAccessIssue]


class FeatureIndex(IntEnum):
    FOUNDRY_CHAT_CLIENT = 48


class RawFoundryChatClient:
    async def _send_request(self) -> None:
        mark_feature_used(FeatureIndex.FOUNDRY_CHAT_CLIENT)
        ...
```

A repository validation test reads every package-local declaration and the
matching language/version table. It fails when an index is out of range, missing
from the registry, duplicated/overlapping across packages, or mapped to the wrong
id. For reference, in v1 `FoundryChatClient` → index 48,
`FoundryAgent` → index 49, Foundry memory → index 50.

### Usage activation points

- **Clients/embeddings/evals:** first outbound operation.
- **Tools/MCP:** first connection, discovery, or invocation that exercises the
  tool surface.
- **Context/history providers:** first provider hook or load/save operation, not
  constructor-only registration.
- **Agents/workflows/orchestrations:** first run/build/start operation that
  activates the defined runtime.
- **Hosting:** first serve/start/route activation.
- **Constructor marking:** allowed only when construction itself performs one of
  those activations or acquires/registers the runtime resource.

## Emission

**One path in v1: the User-Agent `feat=` token, stamped per request on an
explicit allowlist of first-party Azure/Foundry client pipelines only.**

Marking (`mark_feature_used`) is **universal** — every feature sets its index
regardless of provider. Only **emission** is scoped. A user who never calls a
first-party endpoint emits no token; this is the honest, intended behaviour (no
third-party leakage, no signal we couldn't read anyway).

The existing base User-Agent behavior (`agent-framework-python/{version}` plus
any dynamically detected hosting prefix) is unchanged; packages continue using
their current `default_headers`, `user_agent`, suffix, or policy mechanisms.
`get_user_agent()` stays base-only (no `feat=`). The `feat=` token is
**separate**, added **only** by eligible Azure/Foundry clients, and
**re-evaluated on each request** so it reflects the mask accumulated so far. A
helper stamps it:

```python
# agent_framework/_telemetry.py
def apply_feature_token(user_agent: str) -> str:
    """Append/refresh the live ``(feat=v<ver>.<hex>)`` comment on a UA string.

    Re-reads the current mask on every call, so newly accumulated bits are
    reflected immediately. Idempotent: replaces an existing ``(feat=...)``
    comment rather than appending a second.
    """
    token = get_feature_token()  # None when disabled or mask == 0
    base = _strip_feature_comment(user_agent)
    return f"{base} (feat={token})" if token else base
```

Emission requires **both**:

1. an explicitly approved framework client/pipeline family; and
2. the actual request's normalized HTTPS origin matching that family's reviewed
   first-party origin allowlist.

Credentials, `use_azure`, or an Azure-named setting alone do not approve a
destination. Approval depends on the **resolved origin**: customer-specific
subdomains on reviewed Azure/Foundry suffixes remain eligible even when supplied
through `base_url` / `AZURE_OPENAI_BASE_URL`, while customer gateways and unknown
OpenAI-compatible origins are denied by default. The check runs on every actual
request, including redirect hops; a cross-origin or otherwise unapproved redirect
removes `(feat=...)` before sending.

Eligible first-party clients install a **per-request hook** that performs this
classification and calls `apply_feature_token()`:

- **OpenAI-SDK clients created by Agent Framework**: construct the underlying
  client with
  `http_client=DefaultAsyncHttpxClient(event_hooks={"request": [_stamp_feat_hook]})`.
  Using OpenAI's `DefaultAsyncHttpxClient` preserves the SDK's redirect,
  connection-limit, and timeout defaults; a plain `httpx.AsyncClient` must not
  replace them. The hook adds or removes the token based on the approved pipeline
  plus actual-origin classification. Caller-supplied clients/transports are not
  replaced or patched.
- **azure-core pipeline clients**: start with `AIProjectClient` paths whose
  telemetry is confirmed ingestible. When Agent Framework constructs/configures
  an approved pipeline, add a separate per-call `SansIOHTTPPolicy` whose
  `on_request` performs the same actual-origin check and calls
  `apply_feature_token()` on
  `request.http_request.headers["User-Agent"]`. Do not stamp `SearchClient`,
  `CosmosClient`, or another Azure client merely because it is first-party; add
  it to the allowlist only after confirming the data path. This mirrors .NET's
  per-request `PipelinePolicy` exactly.

This fixes the frozen-at-construction problem: the token is materialised at
**send time**, not client-init time, so it carries features activated after the
client was created. It also confines the token to first-party endpoints. Caller-owned
clients are not patched, and toolkit-owned clients without a supported public
hook are outside v1 coverage.

Encoding uses the RFC 7231 **comment** form `(feat=v1.<hex>)` (metadata, not a
product token), placed after the agent-framework product token, e.g.:

```text
foundry-hosting/agent-framework-python/1.2.3 (feat=v1.2a)
```

### OpenTelemetry — not in v1

An OTel span attribute carrying the same value was considered but **deferred —
primarily for privacy, not complexity**. Unlike the first-party-only UA token, a
span attribute broadcasts the feature-combination fingerprint into the user's
**general** telemetry pipeline, which is commonly exported to third-party APM
vendors (Datadog, Honeycomb, …) — re-introducing exactly the leakage the
first-party scoping was chosen to avoid. (It also carries a cardinality footgun:
a monotonically-growing, combinatorial value must never become a metric
dimension.) The version prefix leaves the door open to add it later **if** the
User-Agent path cannot answer a concrete query and there is an acceptable
scoped/redacted variant; v1 ships the UA path only. See
[ADR-0033 → option C](../decisions/0033-feature-usage-bitmask-user-agent.md#considered-options).

## API Changes

New **internal cross-package** surface in
`agent_framework._telemetry` (not exported from `agent_framework`):

- `mark_feature_used(index: int) -> None`
- `get_feature_token() -> str | None` — returns `v<ver>.<hex>` or `None`.
- `apply_feature_token(user_agent: str) -> str` — live, idempotent UA stamper
  used by first-party per-request hooks.
- `FEATURE_MASK_DISABLED_ENV_VAR` constant — the dedicated mask-only opt-out env
  var name (`AGENT_FRAMEWORK_FEATURE_MASK_DISABLED`).

Each package also adds a private package-local `FeatureIndex` declaration for
the rows it owns. Two independent opt-outs gate the mask; see
[Opt-out](#opt-out).

Behavioural change to existing API:

- `get_user_agent()` / `prepend_agent_framework_to_user_agent()` are
  **unchanged** — they keep returning the base UA with no `feat=` token. The
  token is added only by first-party per-request hooks via
  `apply_feature_token()`.

No breaking changes: when the mask is empty or disabled, for any non-first-party
client, or for an injected client outside the supported-hook set, output is
byte-for-byte identical to today.

## Opt-out

Two independent env vars, so users can drop just the mask or the whole UA:

| Env var | Effect |
| --- | --- |
| `AGENT_FRAMEWORK_FEATURE_MASK_DISABLED` | disables **only** the feature mask; the base `agent-framework-python/{version}` User-Agent is still sent |
| `AGENT_FRAMEWORK_USER_AGENT_DISABLED` | disables the **entire** AF User-Agent contribution, mask included |

Both accept `true`/`1` (case-insensitive). The dedicated flag lets a
privacy-conscious user keep contributing the SDK identity/version (useful for
support and compat triage) while withholding the feature-usage signal. The mask
is also disabled implicitly whenever the whole User-Agent is.

## E2E example

```python
from agent_framework import Agent
from agent_framework_foundry import FoundryChatClient
from agent_framework_openai import OpenAIChatClient

# First-party (Foundry) client: per-request hook stamps the live feat token.
agent = Agent(client=FoundryChatClient(...), instructions="...")
# Agent use marks bit 0; FoundryChatClient marks bit 48
await agent.run("Hello")
# Outgoing request to Foundry carries:
#   User-Agent: agent-framework-python/1.2.3 (feat=v1.<mask-at-send-time>)

# Third-party client: NO feat token is added (no first-party hook).
other = Agent(client=OpenAIChatClient(...), instructions="...")
await other.run("Hi")
# Outgoing request to OpenAI carries only:
#   User-Agent: agent-framework-python/1.2.3
```

Drop only the feature mask (keep the base User-Agent):

```bash
AGENT_FRAMEWORK_FEATURE_MASK_DISABLED=true python app.py
# Foundry request User-Agent: agent-framework-python/1.2.3   (no (feat=...) comment)
```

Drop the entire User-Agent contribution (mask included):

```bash
AGENT_FRAMEWORK_USER_AGENT_DISABLED=true python app.py
```

## .NET mapping

- Core owns `FeatureUsage.MarkUsed(int index)` plus the core package's private
  index declaration. Each optional assembly owns a private `FeatureIndex` enum
  containing only its allocated rows. These are index positions `0..127`, not
  `[Flags]` values; `MarkUsed` performs the shift.
- Store the 128-bit mask as **two `long` lanes** (`low` for bits 0–63, `high`
  for 64–127). Marking touches one lane with `Interlocked.Or` where available
  and a small `Interlocked.CompareExchange` loop on `netstandard2.0` / `net472`.
  Read each lane atomically. Since bits only move from zero to one, a concurrent
  two-lane snapshot may miss a just-added bit but can never invent or clear one;
  the next request includes it.
- Format without depending on `UInt128`: if `high == 0`, emit `low` as lowercase
  hex; otherwise emit `high` without leading zeros followed by `low:x16`. Cast
  each signed lane to `ulong` before formatting so bits 63 and 127 are preserved.
  Reject indexes outside `0..127`.
- **Emission is per-request and first-party-scoped**, matching Python. The
  existing `AgentFrameworkUserAgentPolicy` / `HostedAgentUserAgentPolicy`
  pipeline policies already run per request — extend them to apply the same
  approved-pipeline + actual-origin classifier, append/refresh the `(feat=...)`
  comment only for approved destinations, and remove it on unapproved redirect
  hops. Do not register it on third-party `IChatClient`s.
- Same **wire format** (`v<version>.<hex>` comment, hex encoding) and the same
  two opt-out env vars (`AGENT_FRAMEWORK_FEATURE_MASK_DISABLED`,
  `AGENT_FRAMEWORK_USER_AGENT_DISABLED`) in both SDKs — but the **mask is decoded
  per language**: indexes are not shared, so a decoder must read the language from
  the UA product token and select that language's table before decoding. (.NET's
  policy was already per-request, so there is no Python/.NET timing asymmetry.)
  Both environment variables are new behavior for the current .NET policy;
  `AGENT_FRAMEWORK_USER_AGENT_DISABLED` already exists in Python.

## Keeping the bitmap in sync

[feature-usage-bit-registry.md](feature-usage-bit-registry.md) is the published
allocation contract. Package-local `FeatureIndex` declarations are the runtime
implementation. There is deliberately **no shared numbering across languages**
and **no machine-readable registry file**.

One repository validation test gathers every package-local declaration for one
language/version and parses the matching Markdown table. It asserts:

1. every declared index is within `0..127`;
2. every `(index, id)` exactly matches one registry row;
3. the union of declarations has no duplicate/overlapping indexes;
4. every non-reserved registry row is declared exactly once.

Adding an optional-package feature therefore changes that package and the
registry, not core. If a programmatic decoder is built later, export the table
to JSON then.

### Decoding

```
UA: agent-framework-python/1.2.3 (feat=v1.2a)
        │                          │   └ hex mask
        │                          └ version
        └ language → pick the Python table (version 1)
```

Read language → pick the table; read `vN` → pick that version; `AND` the hex mask
against each bit. Unknown bits (from a newer SDK than the decoder's copy of the
table) are ignored.

## Implementation plan (post-approval)

1. **Privacy approval** — confirm the first-party-only feature-combination
   signal, retention, access, allowed queries, and opt-out behavior before code
   ships.
2. **Core accumulator** — in `agent_framework/_telemetry.py` add the 128-bit
   mask, lock, `mark_feature_used(index)`, `get_feature_token`, and
   `apply_feature_token`; `get_user_agent()` stays base-only.
3. **Package-local indexes + validation** — add private `FeatureIndex`
   declarations to packages and a repository test for exact registry parity,
   complete coverage, range, and zero overlap.
4. **First-party per-request hooks** — use OpenAI's
   `DefaultAsyncHttpxClient` for framework-created clients and the separate
   azure-core `SansIOHTTPPolicy`. Require approved pipeline **and** approved
   actual origin on every request/redirect hop. Verify custom origins and
   cross-origin redirects never carry the token.
5. **Mark feature usage** — call `mark_feature_used(FeatureIndex.X)` at the
   first meaningful activation. Operational clients/providers/tools mark on
   their first real operation; build/start points mark compositional features.
   Constructor-only marking requires construction itself to exercise the
   capability.
6. **.NET parity** — package-local index enums plus the two atomic 64-bit lanes
   with `Interlocked.Or` / compare-exchange fallback; extend existing per-request
   Foundry UA policies through the shared destination classifier and formatter.
7. **Docs & tests** — update package `AGENTS.md`/skills; tests for **both**
   opt-out env vars (mask-only and whole-UA), first-party scoping, and the live
   (non-frozen) UA.

## Limitations & open questions

The decision-level limitations and unresolved trade-offs — reach, per-process
(not per-call) attribution, v1 granularity, fingerprinting residue, and the OTel
question — are owned by the ADR (the dedicated mask-only opt-out is now decided
and included). See
**[ADR-0033 → Limitations](../decisions/0033-feature-usage-bitmask-user-agent.md#limitations)**
and **[Open Questions](../decisions/0033-feature-usage-bitmask-user-agent.md#open-questions-for-decider-discussion)**.
This spec is the implementation reference; it does not re-litigate those choices.

Implementation-only note:

- **Per-request hook overhead is negligible** (a flag check, one Python integer
  snapshot or two atomic .NET lane reads, and a string concat per first-party
  request), but benchmark the hot path once if a high-QPS Foundry scenario is in
  scope.
