# Declarative agents and workflows

Use declarative construction when YAML should be the source of truth for supported agent or workflow behavior. Keep
credentials, custom tools, transports, authorization, and application services in code.

## Selection rules

- Use the declarative agent factories in `Microsoft.Agents.AI.Declarative` (for example `ChatClientPromptAgentFactory`
  over an `IChatClient`) for declarative agents, and `Microsoft.Agents.AI.Workflows.Declarative` for declarative
  workflows. Add `Microsoft.Agents.AI.Workflows.Declarative.Foundry` or `.Mcp` only when the definition uses those
  actions.
- Prefer code-first construction when custom C# logic, strong typing, unsupported actions, or dynamic routing would
  make the definition harder to validate than code.
- Do not invent schema kinds or parse definitions into ad hoc constructor calls; use the published schema and factory.
- Declarative workflows evaluate Power Fx expressions (values beginning with `=`); test expressions with realistic
  data and never build expressions from untrusted input.

Package maturity differs per package and surface; check current status and XML docs before making compatibility
commitments.

## Host responsibilities

- Supply the chat clients, project clients, connections, tools, and external handlers the definition references.
- Provide handlers for HTTP, MCP, or Foundry actions when a workflow uses them.
- When using `DefaultHttpRequestHandler`, its client provider is also called for redirect destinations. Return `null`
  to continue with the internal client or throw to reject a destination; returning a client on a redirect is rejected.
- `DefaultHttpRequestHandler` accepts HTTP(S) URLs only and denies every request unless the application supplies
  allowed hosts, for example `new DefaultHttpRequestHandler(["api.example.com"])`. Configure the allowlist in
  trusted application code, not in workflow content. Constructors without an allowlist allow no hosts, even with
  a supplied client or client provider. The handler copies the list and checks it before invoking the provider and
  on every handler-managed redirect.
- Allowed hosts are exact DNS names or IP literals, without schemes, ports, paths, or wildcards. Matching is
  case-insensitive, normalizes internationalized names and trailing DNS dots, and does not implicitly include
  subdomains. A host entry permits both HTTP and HTTPS and any port, subject to existing redirect restrictions.
  Explicitly allowed internal hosts are supported on every target framework. Normal DNS resolution, proxy use,
  and routing are delegated to the HTTP transport; allowing a name trusts the host's DNS and network configuration.
- To supply a client, use `new DefaultHttpRequestHandler(["api.example.com"], httpClient)` or the corresponding
  client-provider overload. Supplied clients must disable automatic redirects or independently enforce the same
  allowlist on redirects, since redirects followed inside a supplied transport are not visible to this handler.
- Keep configuration exposure restricted to intentional values.
- Treat definitions as executable configuration and load them only from trusted sources.
- Allowlist external destinations and register only resources the definition may invoke.
- Review the documented handler ownership rules; use a custom handler when host policy requires different
  authentication, retries, SSRF controls, or transport behavior.

## Validation

Validate definitions at startup and fail clearly on unknown providers, actions, tools, variables, or resources. Apply
the same approval, evaluation, and telemetry policy used for code-first agents and workflows.

`Local` and `Topic` address the same declarative workflow state. On restore, legacy `Topic` entries identified by
declarative sensitivity metadata migrate to `Local` before post-load hooks or resumed actions run. Only migrated
entries are removed from `Topic`; unmarked entries, including code-first state, remain untouched.
Older checkpoints containing an identified declarative key in both physical scopes without canonical ownership
metadata are rejected because assignment order is unavailable. Reconcile those entries explicitly or start a fresh
session before resuming. Legacy entries without declarative metadata require explicit reconciliation rather than
automatic migration.

For code-first executors using the declarative sensitivity helpers without a formula-state restoration callback,
reads fall back to the requested metadata-marked legacy entry without modifying it. Writes use `Local` and remove
only that entry from `Topic`; unrelated legacy entries are not migrated by these point operations.
Ad hoc expression evaluation also reads legacy entries without persisting migration, so parallel expression readers
do not queue competing updates. Persisted migration still runs in registered formula-state restoration callbacks.
New canonical assignments, managed initializations, and migrated entries persist separate, versioned ownership
metadata. This identifies their sensitivity metadata as belonging to `Local`, not to a same-key raw code-first `Topic` entry. Concurrent
code-first `Topic` and canonical `Local` assignments can therefore coexist; reads and restoration preserve the
unrelated raw `Topic` value. Preserve these private metadata scopes together with values in custom checkpoint stores.
Initialization leaves existing values and their sensitivity metadata unchanged. Legacy initialization preserves the
stored native payload even when the caller requests a formula or variant value.
Without recorded canonical ownership, writes still reject a visible same-key unmarked code-first `Topic` entry
before changing state; reconcile such collisions explicitly.

A plain sensitivity-helper null update deletes the canonical value, sensitivity metadata, and ownership metadata.
A wrapped declarative clear retains a blank value with its sensitivity and ownership metadata.

## Learn more

- [Declarative agents](https://learn.microsoft.com/agent-framework/agents/declarative)
- [Declarative workflows](https://learn.microsoft.com/agent-framework/workflows/declarative)
- [Declarative agent samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/DeclarativeAgents)
- [Declarative workflow samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/03-workflows/Declarative)
