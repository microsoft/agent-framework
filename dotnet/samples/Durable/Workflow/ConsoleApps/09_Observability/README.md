# Observability Sample

This sample demonstrates how to enable **OpenTelemetry observability** for durable workflows. It shows how to capture and export traces from workflow execution, including executor dispatch, edge routing, and Durable Task orchestration replays.

## Key Concepts Demonstrated

- Configuring OpenTelemetry tracing for durable workflows
- Subscribing to `Microsoft.Agents.AI.Workflows*` activity sources for workflow-level telemetry
- Exporting traces via OTLP (for Aspire Dashboard)
- Optionally exporting traces to Azure Monitor (Application Insights)
- Correlating all workflow spans under a single trace ID

## Overview

The sample implements a simple text processing pipeline that runs as a durable workflow:

```
UppercaseExecutor --> ReverseTextExecutor
```

| Executor | Description |
|----------|-------------|
| UppercaseExecutor | Converts input text to uppercase |
| ReverseTextExecutor | Reverses the text |

For input `"Hello, World!"`, the workflow produces `"!DLROW ,OLLEH"`.

## Observability Setup

The sample configures OpenTelemetry to capture traces from:

1. **Workflow-level telemetry** (`Microsoft.Agents.AI.Workflows*`): Captures executor execution, edge routing, and workflow lifecycle events.
2. **Durable workflow telemetry** (`Microsoft.Agents.AI.DurableTask*`): Captures durable orchestration lifecycle, executor dispatch, and edge routing within the durable execution environment.
3. **Application-level telemetry**: Custom spans for each workflow invocation with input/output tags.

Traces are exported to:

- **Aspire Dashboard** (default): Via OTLP exporter to `http://localhost:4317`
- **Azure Monitor** (optional): If `APPLICATIONINSIGHTS_CONNECTION_STRING` is set

## Environment Setup

See the [README.md](../README.md) file in the parent directory for information on configuring the Durable Task Scheduler.

### Aspire Dashboard

To visualize traces, start an Aspire Dashboard:

```bash
docker run --rm -it -d -p 18888:18888 -p 4317:18889 --name aspire-dashboard mcr.microsoft.com/dotnet/aspire-dashboard:9.0
```

Then open `http://localhost:18888` in your browser.

Learn more: [Aspire Dashboard Standalone](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone?tabs=bash)

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DURABLE_TASK_SCHEDULER_CONNECTION_STRING` | No | Connection string for the Durable Task Scheduler. Defaults to local emulator. |
| `OTLP_ENDPOINT` | No | OTLP exporter endpoint. Defaults to `http://localhost:4317`. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | No | Application Insights connection string. If set, traces are also sent to Azure Monitor. |

## Running the Sample

```bash
cd dotnet/samples/Durable/Workflow/ConsoleApps/09_Observability
dotnet run --framework net10.0
```

### Sample Output

```text
Operation/Trace ID: abc123def456...

Durable Workflow Observability Sample
Workflow: UppercaseExecutor -> ReverseTextExecutor
Traces are exported via OTLP to: http://localhost:4317

Enter text to process (or 'exit' to quit):
> Hello, World!
Starting workflow for input: "Hello, World!"...
Run ID: xyz789...
Waiting for workflow to complete...
  [UppercaseExecutor] Processing: "Hello, World!"
  [UppercaseExecutor] Result: "HELLO, WORLD!"
  [ReverseTextExecutor] Processing: "HELLO, WORLD!"
  [ReverseTextExecutor] Result: "!DLROW ,OLLEH"
Result: !DLROW ,OLLEH

> exit
```

After running, open the Aspire Dashboard to view the trace. You will see spans for:

- The root `main` activity
- Individual `ProcessText` activities for each invocation
- Workflow executor spans (UppercaseExecutor, ReverseTextExecutor)
- Edge routing spans between executors
