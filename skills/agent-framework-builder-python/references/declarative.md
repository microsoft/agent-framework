# Declarative agents and workflows

Use declarative construction when YAML or JSON should be the source of truth for a supported agent or workflow
definition. Keep credentials, custom tools, transports, authorization, and application services in code.

## Package and maturity

`agent-framework-declarative` is a released distribution:

```bash
uv add agent-framework-declarative
```

Add the selected provider distribution separately. The package being released does not make every API stable:

- Declarative agent loading through `AgentFactory` is experimental.
- Declarative workflow construction through `WorkflowFactory` is not feature-stage decorated.

Check current package and feature maturity before making compatibility commitments.

## Declarative agents

Use `AgentFactory` to create an agent from inline YAML or a file:

```python
import os

from agent_framework.declarative import AgentFactory
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential


client = FoundryChatClient(
    project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
    model=os.environ["FOUNDRY_MODEL"],
    credential=AzureCliCredential(),
)
factory = AgentFactory(client=client)
agent = factory.create_agent_from_yaml_path("agent.yaml")
```

The application remains responsible for provider configuration, credentials, allowed bindings, connections, and
tools. `AgentFactory` emits the experimental feature warning.

See [declarative agents](https://learn.microsoft.com/agent-framework/agents/declarative).

## Declarative workflows

Use `WorkflowFactory` for supported YAML workflow actions:

```python
from agent_framework.declarative import WorkflowFactory


factory = WorkflowFactory()
workflow = factory.create_workflow_from_yaml_path("workflow.yaml")
```

Supply application-owned agents and bindings explicitly. Provide an HTTP or MCP handler when the workflow uses those
actions; build should fail rather than silently dispatch through an unconfigured transport.

See [declarative workflows](https://learn.microsoft.com/agent-framework/workflows/declarative).

## When to stay code-first

Prefer `Agent`, a functional workflow, `WorkflowBuilder`, or an orchestration builder when:

- custom Python logic is the primary behavior;
- direct typing and refactoring matter more than configuration portability;
- the required executor, action, provider, tool, or middleware is not represented by the declarative schema;
- dynamic routing would make the YAML harder to validate than code.

Do not invent unsupported YAML kinds. Use current schema and examples.

## Security and validation

- Treat declarative definitions as executable application configuration.
- Load definitions only from trusted or authenticated sources.
- Keep secrets and credentials outside YAML.
- Keep environment exposure restricted to explicitly supplied configuration by default.
- Allowlist HTTP and MCP destinations.
- Register only the tools, agents, and services the definition may invoke.
- Use custom handlers for authentication, retries, SSRF controls, and connection ownership.
- `DefaultHttpRequestHandler` limits wire and decoded response bodies to 10 MiB by default, including intermediate
  redirect and authentication responses. Set `max_response_body_bytes` when the host requires a different positive
  bound, and do not use response hooks or transports that buffer the body before the handler enforces it.
- Validate at startup and fail clearly on unknown providers, actions, tools, variables, or resources.
- Test declarative agents and workflows with the same approval, evaluation, and telemetry policies as code-first
  construction.
