# Observability

Use observability to diagnose agent runs, model calls, tools, workflows, latency, errors, and token use. It provides
runtime evidence; it does not determine whether output is correct.

## Stable setup rules

- Instrumentation is opt-in per agent: add `UseOpenTelemetry(sourceName, ...)` to an `AIAgentBuilder` (which wraps the
  agent in `OpenTelemetryAgent`) and, for model-call and tool spans, `UseOpenTelemetry(...)` on the `IChatClient`
  pipeline. `HarnessAgent` enables agent telemetry by default and exposes `OpenTelemetrySourceName`.
- The framework emits `ActivitySource` and `Meter` data that follows the generative AI semantic conventions. The
  application must configure the OpenTelemetry SDK and an exporter (OTLP, Azure Monitor, console) and must register the
  same source name with `AddSource(...)` and `AddMeter(...)`; otherwise nothing is collected.
- Configure providers once during startup, using the host's OpenTelemetry setup (`AddOpenTelemetry()`) when running in
  a generic host.
- Keep sensitive payload capture (`EnableSensitiveData`) disabled unless the application explicitly accepts the
  exposure of prompts, responses, and tool arguments.
- Redaction does not replace sanitization in custom telemetry, exporters, middleware, logs (`UseLogging`), or
  exception messages.

Inspect run boundaries, model calls, tool and MCP calls, workflow transitions, checkpoints, approvals, retries, usage,
and hosted-service continuations. Use stable agent, workflow, and service names.

## Learn more

- [Agent observability](https://learn.microsoft.com/agent-framework/agents/observability)
- [Workflow observability](https://learn.microsoft.com/agent-framework/workflows/observability)
- [Agent observability sample](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/Agents/Agent_Step05_Observability)
- [OpenTelemetry demo sample](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/02-agents/AgentOpenTelemetry)
- [Workflow observability samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/03-workflows/Observability)
