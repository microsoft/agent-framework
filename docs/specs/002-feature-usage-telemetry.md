---
status: proposed
contact: eavanvalkenburg
date: 2026-06-12
deciders: eavanvalkenburg
consulted:
informed:
---

# Feature-usage telemetry via an accumulating bitmask

> Companion design for [ADR-0029](../decisions/0029-feature-usage-bitmask-user-agent.md).
> The per-language bit tables, encoding, opt-out, and governance live in
> [feature-usage-bit-registry.md](feature-usage-bit-registry.md). Each SDK's
> hand-written `FeatureBit` enum is the source of truth for that language.

## What is the goal of this feature?

Give the Agent Framework team a lightweight signal about **which framework
features are actually exercised** at runtime (not merely installed), so we can
prioritise investment based on real usage. We emit a single small number — a
*feature mask* — on the User-Agent that already goes out with each request.

**Reach is deliberately bounded.** The mask accumulates from *all* feature usage,
but the `feat=` token is only stamped on requests to **first-party (Azure /
Foundry) endpoints** — the only backends whose telemetry the team can ingest. We
do **not** send the token to third-party providers (OpenAI direct, Anthropic,
Bedrock, Gemini, Ollama, Mistral); doing so would leak a deployment fingerprint
into logs we cannot read (see [Emission](#emission)).

**Granularity is per package**, with core broken out per feature: one bit per
orchestration pattern (sequential / concurrent / group-chat / magentic / handoff)
and **one bit per built-in context/history provider** (memory, skills,
file-access, compaction, todo, agent-mode, background-agents, in-memory/file
history) — because those serve different purposes and we want to know which are
used. See the [registry](feature-usage-bit-registry.md). The question is "are
people using workflows / which orchestration / which providers / MCP / Foundry
memory / Redis?", not which exact subclass. It still fits a 64-bit mask, keeps
the .NET accumulator lock-free, and keeps the registry small enough to
hand-maintain. Finer detail can be earned later via the version prefix.

Success metric: within one release after rollout, ≥80% of first-party (Foundry)
requests carry a **non-empty** feature token whose mask reflects features marked
**after** client construction (i.e. the token is live, not frozen — see the
per-request requirement below). Secondary: ability to break down first-party
traffic by feature combination (e.g. "% of Foundry traffic that also uses
workflows").

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
one module. It owns a process-global 64-bit accumulator. Two env vars can disable
it: the existing `AGENT_FRAMEWORK_USER_AGENT_DISABLED` (which drops the whole
User-Agent contribution, mask included), and a **dedicated**
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


def mark_feature_used(bit: int) -> None:
    """OR a feature bit into the process-global mask.

    Called the first time a feature is exercised. Cheap and idempotent;
    a no-op when the feature mask is disabled.
    """
    global _feature_mask
    if not _feature_mask_enabled():
        return
    with _feature_mask_lock:
        _feature_mask |= 1 << bit


def get_feature_token() -> str | None:
    """Return ``v<version>.<hex_mask>`` for the accumulated mask, or None."""
    if not _feature_mask_enabled() or _feature_mask == 0:
        return None
    return f"v{REGISTRY_VERSION}.{_feature_mask:x}"
```

- **Per package/feature, usage-based:** `mark_feature_used()` is called the first
  time a feature is genuinely exercised — at construction of a representative
  type (e.g. `Agent`, an `MCPTool`, a provider, a Foundry surface), never at
  import time. The mask grows over the process lifetime.
- **Process-global and monotonic — intentionally never reset.** Unlike a
  per-request scheme (e.g. botocore's `contextvars` feature set that resets
  between calls), our mask spans the whole process because many features are not
  bound to any request — an agent, workflow/orchestration, or context/history
  provider is constructed once and used across the session. The single global
  mask is the only scope that can represent them, and its monotonic "usage so
  far" growth is the intended semantic, not a bleed bug. Concurrency-safe via the
  module lock (Python) / `Interlocked.Or` (.NET).
- **Token is safe by construction.** The emitted value is `v{int}.{hex}` —
  characters limited to `[0-9a-fv.]` — so no header-injection sanitization is
  required (contrast botocore, which must sanitize arbitrary component strings).
- **Private API.** `mark_feature_used`, `get_feature_token`, `apply_feature_token`
  and the mask itself are internal helpers; only the emitted token and the
  per-language registry tables are the stable, decodable contract.
- **No import cycles:** the call lives in each package's own module, so `core`
  never imports optional packages. Each package references its bit via the shared
  `FeatureBit` IntEnum exported from `core`.

### Bit constants

`core` exports a hand-written `FeatureBit` IntEnum (defined in `_telemetry.py`
alongside the accumulator). **The enum is the source of truth** for Python; the
Python table in [feature-usage-bit-registry.md](feature-usage-bit-registry.md) is
its published contract, kept aligned in the same PR (see
[Keeping the bitmap in sync](#keeping-the-bitmap-in-sync)). Each package imports
its named member and marks it where the feature is first exercised:

```python
# agent_framework_foundry/_chat_client.py
from agent_framework import FeatureBit, mark_feature_used

class RawFoundryChatClient(...):  # base client; FoundryChatClient builds on it
    def __init__(self, ...):
        mark_feature_used(FeatureBit.FOUNDRY_CHAT_CLIENT)  # bit 22 in v1
        ...
```

Mark in the **`Raw*` base client** (e.g. `RawFoundryChatClient`) so every path
that constructs a Foundry chat client — including the higher-level
`FoundryChatClient` — sets the bit exactly once.

Using the shared enum (not literals) keeps `core` free of optional-package
imports while guaranteeing the bit values match the registry. For reference, in
v1 `FoundryChatClient` → bit 22, `FoundryAgent` → bit 23, Foundry memory → bit 24.

## Emission

**One path in v1: the User-Agent `feat=` token, stamped per request on
first-party (Azure/Foundry) clients only.**

Marking (`mark_feature_used`) is **universal** — every feature sets its bit
regardless of provider. Only **emission** is scoped. A user who never calls a
first-party endpoint emits no token; this is the honest, intended behaviour (no
third-party leakage, no signal we couldn't read anyway).

The base User-Agent (`agent-framework-python/{version}` plus any hosting prefix)
is unchanged and still set once via `default_headers` on **every** client.
`get_user_agent()` stays base-only (no `feat=`). The `feat=` token is **separate**,
added **only** by Azure/Foundry-based clients, and **re-evaluated on each
request** so it reflects the mask accumulated so far. A helper stamps it:

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

Because `default_headers` are static, first-party clients install a
**per-request hook** that calls `apply_feature_token()` on each outgoing request:

- **httpx-based clients** (`AzureOpenAI*` via the `openai` SDK): construct the
  underlying client with
  `http_client=httpx.AsyncClient(event_hooks={"request": [_stamp_feat_hook]})`,
  where the hook mutates `request.headers["User-Agent"]`. Gate on the existing
  `use_azure` signal in `agent_framework_openai/_shared.py` so generic OpenAI
  clients never get the hook.
- **azure-core pipeline clients** (`AIProjectClient`, `SearchClient`,
  `CosmosClient`, …): add a tiny `SansIOHTTPPolicy` whose `on_request` calls
  `apply_feature_token()` on `request.http_request.headers["User-Agent"]`. This
  mirrors .NET's per-request `PipelinePolicy` exactly.

This fixes the frozen-at-construction problem: the token is materialised at
**send time**, not client-init time, so it carries features constructed after the
client. It also confines the token to first-party endpoints.

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
[ADR-0029 → option C](../decisions/0029-feature-usage-bitmask-user-agent.md#considered-options).

## API Changes

New public surface in `agent-framework-core` (exported from
`agent_framework`):

- `mark_feature_used(bit: int) -> None`
- `get_feature_token() -> str | None` — returns `v<ver>.<hex>` or `None`.
- `apply_feature_token(user_agent: str) -> str` — live, idempotent UA stamper
  used by first-party per-request hooks.
- `FeatureBit` (IntEnum) — hand-written source of truth for the Python bit list
  (see [Keeping the bitmap in sync](#keeping-the-bitmap-in-sync)).
- `FEATURE_MASK_DISABLED_ENV_VAR` constant — the dedicated mask-only opt-out env
  var name (`AGENT_FRAMEWORK_FEATURE_MASK_DISABLED`).

Two independent opt-outs gate the mask; see [Opt-out](#opt-out).

Behavioural change to existing API:

- `get_user_agent()` / `prepend_agent_framework_to_user_agent()` are
  **unchanged** — they keep returning the base UA with no `feat=` token. The
  token is added only by first-party per-request hooks via
  `apply_feature_token()`.

No breaking changes: when the mask is empty or disabled, or for any non
first-party client, output is byte-for-byte identical to today.

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
# Agent use marks bit 0; FoundryChatClient marks bit 22
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

- `core` has a hand-written `FeatureBit` enum (`: ulong`) — the **source of
  truth** for the .NET bit list, matching the .NET table in the registry doc —
  plus `FeatureUsage.MarkUsed(FeatureBit)` (universal marking, as in Python).
- 64-bit width means the accumulator is **lock-free**:
  `Interlocked.Or(ref _mask, 1L << (int)bit)`. No lock, no `UInt128`, no
  split-long. The enum value is the bit index; the accumulator ORs the mask value,
  not the raw index.
- **Emission is per-request and first-party-scoped**, matching Python. The
  existing `AgentFrameworkUserAgentPolicy` / `HostedAgentUserAgentPolicy`
  pipeline policies already run per request — extend them to append/refresh the
  `(feat=...)` comment, and register the feat-stamping policy **only on
  Azure/Foundry clients** (e.g. `FoundryChatClient`), not on third-party
  `IChatClient`s.
- Same **wire format** (`v<version>.<hex>` comment, hex encoding) and the same
  two opt-out env vars (`AGENT_FRAMEWORK_FEATURE_MASK_DISABLED`,
  `AGENT_FRAMEWORK_USER_AGENT_DISABLED`) in both SDKs — but the **mask is decoded
  per language**: indexes are not shared, so a decoder must read the language from
  the UA product token and select that language's table before decoding. (.NET's
  policy was already per-request, so there is no Python/.NET timing asymmetry.)

## Keeping the bitmap in sync

The **`FeatureBit` enum in each SDK is the source of truth** for that language.
[feature-usage-bit-registry.md](feature-usage-bit-registry.md) holds the matching
**published table per language** — the contract a decoder reads. There is
deliberately **no shared numbering** and **no machine-readable registry file**: a
Python bit and a .NET bit with the same index need not mean the same thing, and
each SDK adds features without coordinating with the other.

Adding a feature is one PR: add the `FeatureBit` enum member, add the matching
row in that language's table, and mark it at the call site. Review keeps the enum
and table aligned (≈40 entries, changing a few times a year — not worth a
generator or a generated-file drift test). If a programmatic decoder is built
later, export that language's table to JSON for it then.

### Decoding

```
UA: agent-framework-python/1.2.3 (feat=v1.2a)
        │                          │   └ hex mask
        │                          └ version
        └ language → pick the Python table (version 1)
```

Read language → pick the table; read `vN` → pick that version; `AND` the hex mask
against each bit. Unknown high bits (from a newer SDK than the decoder's copy of
the table) are ignored.

## Implementation plan (post-approval)

1. **Core accumulator + enum** — in `agent_framework/_telemetry.py` add the
   64-bit mask, lock, `mark_feature_used`, `get_feature_token`,
   `apply_feature_token`, and the hand-written `FeatureBit` IntEnum (source of
   truth, matching the Python table in the registry doc); `get_user_agent()`
   stays base-only. Unit tests for the live/idempotent stamper.
2. **First-party per-request hooks** — add the httpx `event_hooks` request hook
   (gated on `use_azure` in `agent_framework_openai/_shared.py`) and the
   azure-core `SansIOHTTPPolicy` (for `AIProjectClient`/`SearchClient`/Cosmos).
   Verify against a real Foundry call that the UA carries a **non-empty,
   post-construction** mask. **Do not** add hooks to third-party clients.
3. **Mark feature usage** — call `mark_feature_used(FeatureBit.X)` once per
   feature, the first time it is exercised: at the **`Raw*` base client/entry
   point** per package (e.g. `RawFoundryChatClient`) so every higher-level
   wrapper inherits the marking, and in the `__init__` of **each** core
   construct that owns a bit — including every built-in context/history provider
   (memory, skills, file-access, compaction, todo, agent-mode, background-agents,
   in-memory/file history) and each orchestration builder. Marking is universal;
   emission stays first-party-only.
4. **.NET parity** — hand-written `FeatureBit : ulong` enum (source of truth for
   the .NET table); `FeatureUsage.MarkUsed` with lock-free `Interlocked.Or`;
   extend the existing per-request UA policy to stamp `(feat=...)` **only on
   Azure/Foundry clients**. The .NET enum is **independent** of Python's.
5. **Docs & tests** — update package `AGENTS.md`/skills; tests for **both**
   opt-out env vars (mask-only and whole-UA), first-party scoping, and the live
   (non-frozen) UA.

## Limitations & open questions

The decision-level limitations and unresolved trade-offs — reach, per-process
(not per-call) attribution, v1 granularity, fingerprinting residue, and the OTel
question — are owned by the ADR (the dedicated mask-only opt-out is now decided
and included). See
**[ADR-0029 → Limitations](../decisions/0029-feature-usage-bitmask-user-agent.md#limitations)**
and **[Open Questions](../decisions/0029-feature-usage-bitmask-user-agent.md#open-questions-for-decider-discussion)**.
This spec is the implementation reference; it does not re-litigate those choices.

Implementation-only note:

- **Per-request hook overhead is negligible** (a flag check, a lock-free read of
  the mask, and a string concat per first-party request), but benchmark the hot
  path once if a high-QPS Foundry scenario is in scope.
