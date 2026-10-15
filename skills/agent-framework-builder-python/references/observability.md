# Observability

Use observability to diagnose agent runs, model calls, tools, workflows, latency, errors, and token use. It provides
runtime evidence; it does not determine whether output is correct.

## Stable setup rules

- Agent Framework instrumentation is enabled by default, but applications must configure OpenTelemetry providers and
  exporters.
- Narrow installations include `opentelemetry-api`, not the SDK. Install `opentelemetry-sdk` and the exporter required
  by the chosen backend.
- Configure providers once during startup, or use application-owned OpenTelemetry setup and enable Agent Framework
  instrumentation against it.
- Keep sensitive payload capture disabled unless the application explicitly accepts the exposure.
- Built-in redaction does not replace sanitization in custom telemetry, exporters, middleware, or exception messages.

Inspect run boundaries, model calls, tool and MCP calls, workflow transitions, checkpoints, approvals, retries, usage,
and hosted-service continuations. Use stable agent, workflow, and service identifiers.

## Learn more

- [Agent observability](https://learn.microsoft.com/agent-framework/agents/observability)
- [Workflow observability](https://learn.microsoft.com/agent-framework/workflows/observability)
- [Observability samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/observability)
