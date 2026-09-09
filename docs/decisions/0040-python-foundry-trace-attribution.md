---
status: proposed
contact: jpalvarezl
date: 2026-09-09
deciders: [eavanvalkenburg, moonbox3]
---

# Separate Foundry trace attribution from exporter configuration

## Context and Problem Statement

[Issue #7492](https://github.com/microsoft/agent-framework/issues/7492) reports
client spans reaching Application Insights but missing from the Foundry agent
trace view. Exporting telemetry and identifying the project/agent represented
by an operation are separate concerns.

The initial fix in [PR #7981](https://github.com/microsoft/agent-framework/pull/7981)
resolved project identity only through `FoundryAgent.configure_azure_monitor()`.
That left applications configuring their own exporters without an attribution
path. It also let optional identity-discovery failures abort usable export.
Separately, recording the last child chat's response ID could assign an
after-run provider's ID to the agent invocation.

## Decision Drivers

- Support application-managed exporters without reconfiguring global providers.
- Keep identity scoped to the agent/project rather than a process-wide setting.
- Preserve export when optional metadata discovery fails, with a visible warning.
- Use the completed agent-owned operation for response identity.
- Preserve public response-ID suppression, continuation, and usage semantics.
- Do not generalize one successful root-span arrangement into a universal
  requirement that every application root carry project attributes.

## Considered Options

- **Helper-only discovery.** Simple, but couples identity to one exporter helper
  and leaves application-managed configurations unsupported.
- **Automatic discovery on each run.** Convenient, but introduces implicit
  network work, latency, and failure handling into the invocation path.
- **Explicit per-agent identity plus cached helper discovery.** Supports both
  setup styles without run-time discovery. Applications using their own
  exporters must supply the project ARM ID.

## Decision Outcome

Choose **explicit per-agent identity plus cached helper discovery**:

- Add keyword-only `project_arm_id` to `RawFoundryAgent` and `FoundryAgent`.
  The full project ARM ID is validated at construction; it is not inferred from
  the data-plane endpoint or read implicitly from an environment variable.
- `FoundryAgent` emits the project attribute alongside agent identity on its
  `invoke_agent` span, which may be nested beneath an application span.
- The Azure Monitor helper discovers and caches identity only when no ID was
  supplied. Expected discovery/metadata errors log a warning and preserve
  export; unexpected programming errors and cancellation still propagate.
- Capture response identity from the agent-owned chat result before conversion
  and after-run callbacks. In streaming, use the underlying final response,
  including finalizer-only metadata. Keep this private telemetry identity
  separate from the public response/continuation fields.
- Consolidate invocation bookkeeping into one owner-scoped context state.
  Child chats can still contribute usage without choosing the agent's identity.

The public SDK does not yet expose project identity directly
([Azure/azure-sdk-for-python#48825](https://github.com/Azure/azure-sdk-for-python/issues/48825)).
Connection-ID parsing remains a bounded discovery workaround, not a requirement
for applications that already know their project ARM ID.

Acceptance distinguishes local emission, Application Insights ingestion, and
personal inspection of client spans in Foundry. Supported examples use full
project ARM IDs; alternate formats and service-side legacy-key behavior are not
new guarantees of this API.
