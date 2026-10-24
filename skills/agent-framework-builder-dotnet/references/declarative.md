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
- Keep configuration exposure restricted to intentional values.
- Treat definitions as executable configuration and load them only from trusted sources.
- Allowlist external destinations and register only resources the definition may invoke.
- Review the documented handler ownership rules; use a custom handler when host policy requires different
  authentication, retries, SSRF controls, or transport behavior.

## Validation

Validate definitions at startup and fail clearly on unknown providers, actions, tools, variables, or resources. Apply
the same approval, evaluation, and telemetry policy used for code-first agents and workflows.

## Learn more

- [Declarative agents](https://learn.microsoft.com/agent-framework/agents/declarative)
- [Declarative workflows](https://learn.microsoft.com/agent-framework/workflows/declarative)
- [Declarative agent samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/DeclarativeAgents)
- [Declarative workflow samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/03-workflows/Declarative)
