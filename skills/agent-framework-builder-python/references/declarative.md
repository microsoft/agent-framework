# Declarative agents and workflows

Use declarative construction when YAML or JSON should be the source of truth for supported agent or workflow behavior.
Keep credentials, custom tools, transports, authorization, and application services in code.

## Selection rules

- Use `AgentFactory` for declarative agents and `WorkflowFactory` for declarative workflows.
- Prefer code-first construction when custom Python logic, strong typing, unsupported actions, or dynamic routing would
  make the definition harder to validate than code.
- Do not invent schema kinds or parse definitions into ad hoc constructor calls; use the published schema and factory.
- Use Python 3.13 or earlier when definitions rely on Power Fx expressions (values beginning with `=`). On Python 3.14
  and 3.15, the optional `powerfx` dependency is unavailable, so those values emit a warning and remain unevaluated.

The `agent-framework-declarative` distribution is released, but individual surfaces can have different feature
maturity. Check current package status and public docstrings before making compatibility commitments.

## Host responsibilities

- Supply provider clients, connections, bindings, tools, and external handlers explicitly.
- Provide an HTTP or MCP handler when a workflow uses those actions.
- Keep environment exposure restricted to intentional configuration.
- Treat definitions as executable configuration and load them only from trusted sources.
- Allowlist external destinations and register only resources the definition may invoke.
- Review the documented HTTP body limits and handler ownership rules; use a custom handler when host policy requires
  different authentication, retries, SSRF controls, or transport behavior.
- Direct `DefaultMCPToolHandler` calls without a non-empty `workflow_session_id` use a fresh session per invocation;
  only explicitly scoped calls without a client provider reuse cached MCP sessions.
- Declarative children wrapped in `WorkflowExecutor` retain MCP session continuity across parent agent turns.
  Each binding must own a unique child workflow instance; its MCP scope remains isolated from sibling bindings.
  Replaying a parent entry checkpoint also retains child scopes when rebuilding the same workflow graph.
  Child responses restore the originating parent scope before invoking downstream bindings, including after
  checkpoint restoration. Submit responses from different parent scopes in separate runs.

## Validation

Validate definitions at startup and fail clearly on unknown providers, actions, tools, variables, or resources. Apply
the same approval, evaluation, and telemetry policy used for code-first agents and workflows.

## Learn more

- [Declarative agents](https://learn.microsoft.com/agent-framework/agents/declarative)
- [Declarative workflows](https://learn.microsoft.com/agent-framework/workflows/declarative)
- [Declarative package README](https://github.com/microsoft/agent-framework/blob/main/python/packages/declarative/README.md)
- [Declarative samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/declarative)
