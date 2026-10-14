# Observability

Use observability to diagnose and monitor agent runs, model calls, tool calls, workflow execution, latency, errors, and
token use. Observability provides runtime evidence; it does not define whether an output is correct.

## OpenTelemetry configuration

Agent Framework instrumentation is enabled by default, but the application must configure OpenTelemetry providers and
exporters. The helper below configures them from arguments and standard environment variables:

```python
from agent_framework.observability import configure_otel_providers


configure_otel_providers(enable_sensitive_data=False)
```

- Call `configure_otel_providers(...)` once during application startup.
- Keep sensitive prompts, tool arguments, tool results, and model responses disabled by default.
- Use `enable_instrumentation(...)` only to control instrumentation when providers are configured elsewhere.
- Use traces to correlate agent runs, model calls, tools, MCP calls, and workflow executors.
- Give agents, harnesses, workflows, and services stable identifiers.
- When sensitive data is disabled, built-in Agent Framework telemetry redacts exception details from spans, events,
  workflow telemetry, and failure logs, and does not attach serialized tool arguments to invocation metrics.
- Apply equivalent redaction and cardinality controls to application-defined telemetry and custom exporters.

## What to inspect

- Agent and workflow run boundaries.
- Model requests, responses, latency, and token usage.
- Function and MCP tool calls, including failures and approval pauses.
- Workflow executor transitions, checkpoint activity, and suspended runs.
- Provider errors, retries, and hosted-service continuations.

Avoid using telemetry as a storage mechanism for application state or sensitive conversation history.

See [agent observability](https://learn.microsoft.com/agent-framework/agents/observability) and
[workflow observability](https://learn.microsoft.com/agent-framework/workflows/observability).

Current examples:

- [Agent observability](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/observability/agent_observability.py)
- [Workflow observability](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/observability/workflow_observability.py)
