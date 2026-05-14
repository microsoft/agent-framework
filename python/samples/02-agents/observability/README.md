# Agent Framework Observability

These samples show how to send Agent Framework observability data to the Application Performance Management (APM) backend of your choice, based on the OpenTelemetry standard.

The samples target [Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview), the [Aspire Dashboard](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/overview?tabs=bash), and the console, but any OTLP-compatible backend works.

> **Quick Start**: For local development without Azure setup, use the [Aspire Dashboard](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone) (runs locally via Docker), or the built-in tracing module of the [AI Toolkit for VS Code](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio).

> Other backends such as [Prometheus](https://prometheus.io/docs/introduction/overview/) are also supported. See the [OpenTelemetry Python exporters](https://opentelemetry.io/docs/languages/python/exporters/) page for the full list.

For more information, please refer to the following resources:

1. [Azure Monitor OpenTelemetry Exporter](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/monitor/azure-monitor-opentelemetry-exporter)
2. [Aspire Dashboard for Python Apps](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone-for-python?tabs=flask%2Cwindows)
3. [AI Toolkit for VS Code](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)
4. [Python Logging](https://docs.python.org/3/library/logging.html)
5. [Observability in Python](https://www.cncf.io/blog/2022/04/22/opentelemetry-and-python-a-complete-instrumentation-guide/)

## What to expect

The Agent Framework Python SDK is **natively instrumented** to emit logs, traces, and metrics throughout agent/model invocation and tool execution, so you can monitor your AI application's performance and track token consumption. Instrumentation follows the OpenTelemetry [Semantic Conventions for GenAI](https://opentelemetry.io/docs/specs/semconv/gen-ai/), and workflows emit their own spans for end-to-end visibility.

Setting up observability is also easy: a single call to `configure_otel_providers()` from the `agent_framework.observability` module wires up the trace, log, and metric providers. It reads the standard OpenTelemetry environment variables to configure exporters automatically.

### Five patterns for configuring observability

> Setting up observability has two parts: (1) **instrumentation**, the code that generates telemetry, and (2) **exporter/provider configuration**, which decides where that telemetry is sent. Agent Framework is natively instrumented and **enabled by default**, so you only need to handle the second part.

There are five common ways to do that, depending on your needs:

**1. Standard otel environment variables, configured for you**

The simplest approach - configure everything via environment variables:

```python
from agent_framework.observability import configure_otel_providers

# Reads OTEL_EXPORTER_OTLP_* environment variables automatically
configure_otel_providers()
```

Or if you just want console exporters:

```python
from agent_framework.observability import configure_otel_providers

configure_otel_providers(enable_console_exporters=True)
# It is also possible to set ENABLE_CONSOLE_EXPORTERS=true in environment
# variables instead of calling `configure_otel_providers()` with the parameter.
# The framework will automatically read that and set up console exporters.
```

This is the **recommended approach** for getting started.

**2. Custom Exporters**

For more control, construct exporters yourself and pass them to `configure_otel_providers()`. The framework still creates the providers for you:

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.exporter import Compression
from agent_framework.observability import configure_otel_providers

# Create custom exporters with specific configuration
exporters = [
    OTLPSpanExporter(endpoint="http://localhost:4317", compression=Compression.Gzip),
    OTLPLogExporter(endpoint="http://localhost:4317"),
    OTLPMetricExporter(endpoint="http://localhost:4317"),
]

# These are added alongside any exporters configured from environment variables
configure_otel_providers(exporters=exporters)
```

**3. Third-party setup**

Many third-party OTel packages ship their own setup helpers (for example, Azure Monitor's `configure_azure_monitor()`). You can use those directly — Agent Framework instrumentation is on by default, so no extra wiring is needed. To also capture sensitive data, call `enable_sensitive_telemetry()` from `agent_framework.observability`.

```python
from azure.monitor.opentelemetry import configure_azure_monitor
from agent_framework.observability import create_resource, enable_sensitive_telemetry

# Configure Azure Monitor first
configure_azure_monitor(
    connection_string="InstrumentationKey=...",
    resource=create_resource(),  # Uses OTEL_SERVICE_NAME, etc.
    enable_live_metrics=True,
)

# Optional: opt in to capturing sensitive data
enable_sensitive_telemetry()
```

For Microsoft Foundry projects, use `client.configure_azure_monitor()` which retrieves the connection string from the project and configures everything:

```python
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

client = FoundryChatClient(
    project_endpoint="https://your-project.services.ai.azure.com",
    model="gpt-4o",
    credential=AzureCliCredential(),
)

# Automatically configures Azure Monitor with connection string from project
await client.configure_azure_monitor(enable_sensitive_data=True)
```

Or with [Langfuse](https://langfuse.com/integrations/frameworks/microsoft-agent-framework):

```python
# environment should be setup correctly, with langfuse urls and keys
from agent_framework.observability import enable_sensitive_telemetry
from langfuse import get_client

langfuse = get_client()

# Verify connection
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")

# Agent Framework instrumentation is on by default.
# Optional: opt in to capturing sensitive data
enable_sensitive_telemetry()
```

Or with [Comet Opik](https://www.comet.com/docs/opik/integrations/microsoft-agent-framework):

```python
import os

from agent_framework.observability import enable_sensitive_telemetry

# Use Opik OTLP settings from your project settings
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "<opik_otlp_endpoint>"
os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = "<opik_otlp_headers>"

# Agent Framework instrumentation is on by default.
# Optional: opt in to capturing sensitive data
enable_sensitive_telemetry()
```

**4. Manual setup**

For full control, set up providers and exporters yourself. See [advanced_manual_setup_console_output.py](./advanced_manual_setup_console_output.py) for a complete example that sends traces, logs, and metrics to the console. The `create_resource()` helper in `agent_framework.observability` can build a resource with the appropriate service name and version from environment variables (or sensible defaults), although the sample does not use it.

**5. Zero-code provider/exporter configuration**

Because Agent Framework is **natively instrumented** with OpenTelemetry, you do not need to auto-instrument the framework itself. You can, however, use the [`opentelemetry-instrument`](https://opentelemetry.io/docs/zero-code/python/) CLI wrapper to configure the global tracer/meter providers and exporters from environment variables (or CLI flags) at process startup. Your application code then does not need to call `configure_otel_providers()` — the native spans and metrics from Agent Framework are picked up by the globally configured pipeline. See [advanced_zero_code.py](./advanced_zero_code.py) for an example.

### MCP trace propagation

Whenever there is an active OpenTelemetry span context, Agent Framework automatically propagates trace context to MCP servers via the `params._meta` field of `tools/call` requests. It uses the globally configured OpenTelemetry propagator(s) — W3C Trace Context by default (producing `traceparent` and `tracestate`) — so custom propagators (B3, Jaeger, etc.) are also supported. This enables distributed tracing across agent-to-MCP-server boundaries, compliant with the [MCP `_meta` specification](https://modelcontextprotocol.io/specification/2025-11-25/basic#_meta).

**Scope:** automatic `_meta` injection applies only to MCP sessions that the agent process itself opens — `MCPStreamableHTTPTool`, `MCPStdioTool`, and `MCPWebsocketTool` (or any other client-opened `MCPTool` subclass). It does **not** apply to hosted or provider-managed MCP tool configurations such as `FoundryChatClient.get_mcp_tool(...)`, `OpenAIChatClient.get_mcp_tool(...)`, `AnthropicClient.get_mcp_tool(...)`, `GeminiChatClient.get_mcp_tool(...)`, or toolbox-fetched tools (e.g. `toolbox = await client.get_toolbox(...)` then `Agent(tools=toolbox.tools)`). In those cases the `tools/call` message is issued by the provider service runtime rather than by the agent process, so propagating `traceparent`/`tracestate` across that boundary is the service runtime's responsibility. If you need end-to-end distributed tracing to the downstream MCP server, use a client-opened MCP transport instead of a hosted connector.

## Configuration

### Dependencies

Agent Framework depends on the following OpenTelemetry packages:
- `opentelemetry-api`
- `opentelemetry-sdk`
- `opentelemetry-semantic-conventions-ai`

Exporters are **not** installed by default — install only what you need:
- **Application Insights**: `azure-monitor-opentelemetry`
- **Aspire Dashboard or other OTLP/gRPC backends**: `opentelemetry-exporter-otlp-proto-grpc`
- **OTLP over HTTP**: `opentelemetry-exporter-otlp-proto-http`

For other backends, refer to the documentation of the specific exporter.

### Environment variables

Agent Framework reads the following environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_INSTRUMENTATION` | `true` | Set to `false` to disable native instrumentation. |
| `ENABLE_SENSITIVE_DATA` | `false` | Set to `true` to emit sensitive data (prompts, responses, etc.). |
| `ENABLE_CONSOLE_EXPORTERS` | `false` | Set to `true` to add console exporters. Only used by `configure_otel_providers()`. |
| `VS_CODE_EXTENSION_PORT` | unset | Port used by the [AI Toolkit for VS Code](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio#tracing) tracing integration. Only used by `configure_otel_providers()`. |

You can also call `enable_sensitive_telemetry()` from `agent_framework.observability` to opt in to sensitive-data capture programmatically.

> **Note**: Sensitive data includes prompts, responses, and tool arguments. Only enable it in development or test environments — it may expose user or system secrets in production.

#### Environment variables for `configure_otel_providers()`

The `configure_otel_providers()` function automatically reads **standard OpenTelemetry environment variables** to configure exporters:

**OTLP Configuration** (for Aspire Dashboard, Jaeger, etc.):
- `OTEL_EXPORTER_OTLP_ENDPOINT` - Base endpoint for all signals (e.g., `http://localhost:4317`)
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` - Traces-specific endpoint (overrides base)
- `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` - Metrics-specific endpoint (overrides base)
- `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` - Logs-specific endpoint (overrides base)
- `OTEL_EXPORTER_OTLP_PROTOCOL` - Protocol to use (`grpc` or `http`, default: `grpc`)
- `OTEL_EXPORTER_OTLP_HEADERS` - Headers for all signals (e.g., `key1=value1,key2=value2`)
- `OTEL_EXPORTER_OTLP_TRACES_HEADERS` - Traces-specific headers (overrides base)
- `OTEL_EXPORTER_OTLP_METRICS_HEADERS` - Metrics-specific headers (overrides base)
- `OTEL_EXPORTER_OTLP_LOGS_HEADERS` - Logs-specific headers (overrides base)

**Service Identification**:
- `OTEL_SERVICE_NAME` - Service name (default: `agent_framework`)
- `OTEL_SERVICE_VERSION` - Service version (default: package version)
- `OTEL_RESOURCE_ATTRIBUTES` - Additional resource attributes (e.g., `key1=value1,key2=value2`)

> **Note**: These are standard OpenTelemetry environment variables. See the [OpenTelemetry spec](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/) for more details.

#### Logging

Use standard Python logging configuration to align logs with telemetry output:

```python
import logging

logging.basicConfig(
    format="[%(asctime)s - %(pathname)s:%(lineno)d - %(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
```

To control which logs are exported, adjust the root logger level — other loggers inherit from it by default:

```python
import logging

logging.getLogger().setLevel(logging.NOTSET)
```

## Samples

This folder contains different samples demonstrating how to use telemetry in various scenarios.

| Sample | Description |
|--------|-------------|
| [configure_otel_providers_with_env_var.py](./configure_otel_providers_with_env_var.py) | **Recommended starting point**: configure telemetry using standard OpenTelemetry environment variables (`OTEL_EXPORTER_OTLP_*`). |
| [configure_otel_providers_with_parameters.py](./configure_otel_providers_with_parameters.py) | Create custom exporters with specific configuration and pass them to `configure_otel_providers()`. |
| [agent_observability.py](./agent_observability.py) | Telemetry collection for an agentic application with tool calls. |
| [foundry_tracing.py](./foundry_tracing.py) | Azure Monitor integration with Microsoft Foundry. |
| [workflow_observability.py](./workflow_observability.py) | Telemetry collection for a workflow with multiple executors and message passing. |
| [advanced_manual_setup_console_output.py](./advanced_manual_setup_console_output.py) | Advanced: manual setup of exporters and providers with console output — useful for understanding how observability works under the hood. |
| [advanced_zero_code.py](./advanced_zero_code.py) | Advanced: zero-code provider/exporter setup using the `opentelemetry-instrument` CLI wrapper. |

### Running the samples

1. Open a terminal in this folder (`python/samples/02-agents/observability/`) so that `.env` is found.
2. Create a `.env` file if you don't already have one. See [.env.example](./.env.example).
    > Instrumentation is on by default. Set `OTEL_EXPORTER_OTLP_ENDPOINT` (or other configuration) as needed. With no exporters configured, set `ENABLE_CONSOLE_EXPORTERS=true` for console output.
3. Pick an environment-loading approach:
    - **A. Sample-managed:** run from this folder so the sample's `load_dotenv()` call can find `.env`.
    - **B. Shell/IDE-managed:** export environment variables, or use an IDE run configuration that injects them.
    - **C. Explicit env file in code:** pass `env_file_path` to APIs like `configure_otel_providers(env_file_path=".env")`.
    - **D. CLI-managed:** run with `uv` and pass the file explicitly, e.g. `uv run --env-file=.env python configure_otel_providers_with_env_var.py`.
4. Activate your virtual environment, then run a sample (e.g. `python configure_otel_providers_with_env_var.py`).

> If you set up providers manually (e.g. Azure Monitor), Agent Framework instrumentation is still on by default. Call `enable_sensitive_telemetry()` if you also want to capture sensitive data. To have Agent Framework configure exporters and providers for you, call `configure_otel_providers(...)`.

> Each sample prints its Operation/Trace ID, which you can use to filter logs and traces in Application Insights or the Aspire Dashboard.

# Appendix

## Azure Monitor Queries

For an overall view of a span in Azure Monitor, run this query in the Logs section:

```kusto
dependencies
| where operation_Id in (dependencies
    | project operation_Id, timestamp
    | order by timestamp desc
    | summarize operations = make_set(operation_Id), timestamp = max(timestamp) by operation_Id
    | order by timestamp desc
    | project operation_Id
    | take 2)
| evaluate bag_unpack(customDimensions)
| extend tool_call_id = tostring(["gen_ai.tool.call.id"])
| join kind=leftouter (customMetrics
    | extend tool_call_id = tostring(customDimensions['gen_ai.tool.call.id'])
    | where isnotempty(tool_call_id)
    | project tool_call_duration = value, tool_call_id)
    on tool_call_id
| project-keep timestamp, target, operation_Id, tool_call_duration, duration, gen_ai*
| order by timestamp asc
```

### Grafana dashboards with Application Insights data

In addition to the native Application Insights UI, you can use Grafana to visualize the same telemetry data. Two tailored dashboards are available to get you started:

#### Agent Overview dashboard
Open dashboard in Azure portal: <https://aka.ms/amg/dash/af-agent>
![Agent Overview dashboard](https://github.com/Azure/azure-managed-grafana/raw/main/samples/assets/grafana-af-agent.gif)

#### Workflow Overview dashboard
Open dashboard in Azure portal: <https://aka.ms/amg/dash/af-workflow>
![Workflow Overview dashboard](https://github.com/Azure/azure-managed-grafana/raw/main/samples/assets/grafana-af-workflow.gif)

## Migration Guide

The observability API has been overhauled. The new API simplifies configuration by relying on standard OpenTelemetry environment variables and separates instrumentation from configuration.

If you're updating from an earlier version of Agent Framework, here are the key changes:

### Environment Variables

| Old Variable | New Variable | Notes |
|-------------|--------------|-------|
| `OTLP_ENDPOINT` | `OTEL_EXPORTER_OTLP_ENDPOINT` | Standard OpenTelemetry env var |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | N/A | Use `configure_azure_monitor()` |
| N/A | `ENABLE_CONSOLE_EXPORTERS` | New opt-in flag for console output |

### OTLP Configuration

**Before (Deprecated):**
```
from agent_framework.observability import setup_observability
# Via parameter
setup_observability(otlp_endpoint="http://localhost:4317")

# Via environment variable
# OTLP_ENDPOINT=http://localhost:4317
setup_observability()
```

**After (Current):**
```python
from agent_framework.observability import configure_otel_providers
# Via standard OTEL environment variable (recommended)
# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
configure_otel_providers()

# Or via custom exporters
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

configure_otel_providers(exporters=[
    OTLPSpanExporter(endpoint="http://localhost:4317"),
    OTLPLogExporter(endpoint="http://localhost:4317"),
    OTLPMetricExporter(endpoint="http://localhost:4317"),
])
```

### Azure Monitor Configuration

**Before (Deprecated):**
```
from agent_framework.observability import setup_observability

setup_observability(
    applicationinsights_connection_string="InstrumentationKey=...",
    applicationinsights_live_metrics=True,
)
```

**After (Current):**

```python
from agent_framework.foundry import FoundryChatClient
from agent_framework.observability import create_resource, enable_sensitive_telemetry
from azure.identity import AzureCliCredential
from azure.monitor.opentelemetry import configure_azure_monitor

async def main():
    # For Microsoft Foundry projects
    client = FoundryChatClient(
        project_endpoint="https://your-project.services.ai.azure.com",
        model="gpt-4o",
        credential=AzureCliCredential(),
    )
    await client.configure_azure_monitor(enable_live_metrics=True)

    # For non-Azure AI projects
    configure_azure_monitor(
        connection_string="InstrumentationKey=...",
        resource=create_resource(),
        enable_live_metrics=True,
    )
    # Optional: opt in to capturing sensitive data
    enable_sensitive_telemetry()
```

### Console Output

**Before (Deprecated):**
```
from agent_framework.observability import setup_observability

# Console was used as automatic fallback
setup_observability()  # Would output to console if no exporters configured
```

**After (Current):**
```python
from agent_framework.observability import configure_otel_providers

# Console exporters are now opt-in
# ENABLE_CONSOLE_EXPORTERS=true
configure_otel_providers()

# Or programmatically
configure_otel_providers(enable_console_exporters=True)
```

### Benefits of New API

1. **Standards Compliant**: Uses standard OpenTelemetry environment variables
2. **Simpler**: Less configuration needed, more relies on environment
3. **Flexible**: Easy to add custom exporters alongside environment-based ones
4. **Cleaner Separation**: Azure Monitor setup is in Azure-specific client
5. **Better Compatibility**: Works with any OTEL-compatible tool (Jaeger, Zipkin, Prometheus, etc.)

## Aspire Dashboard

The [Aspire Dashboard](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone) is a local telemetry viewing tool that provides an excellent experience for viewing OpenTelemetry data without requiring Azure setup.

### Setting up Aspire Dashboard with Docker

The easiest way to run the Aspire Dashboard locally is using Docker:

```bash
# Pull and run the Aspire Dashboard container
docker run --rm -it -d \
    -p 18888:18888 \
    -p 4317:18889 \
    --name aspire-dashboard \
    mcr.microsoft.com/dotnet/aspire-dashboard:latest
```

This will start the dashboard with:

- **Web UI**: Available at <http://localhost:18888>
- **OTLP endpoint**: Available at `http://localhost:4317` for your applications to send telemetry data

### Configuring your application

Make sure your `.env` file includes the OTLP endpoint:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

Or set it as an environment variable when running your samples:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 python configure_otel_providers_with_env_var.py
```

### Viewing telemetry data

> Make sure you have the dashboard running to receive telemetry data.

Once your sample finishes running, navigate to <http://localhost:18888> in a web browser to see the telemetry data. Follow the [Aspire Dashboard exploration guide](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/explore) to authenticate to the dashboard and start exploring your traces, logs, and metrics!
