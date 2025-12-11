# Agent Framework Python Observability

This sample folder shows how a Python application can be configured to send Agent Framework observability data to the Application Performance Management (APM) vendor(s) of your choice based on the OpenTelemetry standard.

In this sample, we provide options to send telemetry to [Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview), [Aspire Dashboard](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/overview?tabs=bash) and the console.

> **Quick Start**: For local development without Azure setup, you can use the [Aspire Dashboard](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone) which runs locally via Docker and provides an excellent telemetry viewing experience for OpenTelemetry data. Or you can use the built-in tracing module of the [AI Toolkit for VS Code](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio).

> Note that it is also possible to use other Application Performance Management (APM) vendors. An example is [Prometheus](https://prometheus.io/docs/introduction/overview/). Please refer to this [page](https://opentelemetry.io/docs/languages/python/exporters/) to learn more about exporters.

For more information, please refer to the following resources:

1. [Azure Monitor OpenTelemetry Exporter](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/monitor/azure-monitor-opentelemetry-exporter)
2. [Aspire Dashboard for Python Apps](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone-for-python?tabs=flask%2Cwindows)
3. [AI Toolkit for VS Code](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)
4. [Python Logging](https://docs.python.org/3/library/logging.html)
5. [Observability in Python](https://www.cncf.io/blog/2022/04/22/opentelemetry-and-python-a-complete-instrumentation-guide/)

## What to expect

The Agent Framework Python SDK is designed to efficiently generate comprehensive logs, traces, and metrics throughout the flow of agent/model invocation and tool execution. This allows you to effectively monitor your AI application's performance and accurately track token consumption. It does so based on the Semantic Conventions for GenAI defined by OpenTelemetry, and the workflows emit their own spans to provide end-to-end visibility.

## Configuration

### Required resources

1. OpenAI or [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/create-resource?pivots=web-portal)
2. An [Azure AI project](https://ai.azure.com/doc/azure/ai-foundry/what-is-azure-ai-foundry)

### Optional resources

The following resources are needed if you want to send telemetry data to them:

1. [Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/create-workspace-resource)
2. [Aspire Dashboard](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone-for-python?tabs=flask%2Cwindows#start-the-aspire-dashboard)

### Dependencies

No additional dependencies are required to enable telemetry. The necessary packages are included as part of the `agent-framework` package. Unless you want to use a different APM vendor, in which case you will need to install the appropriate OpenTelemetry exporter package.

### Environment variables

The following environment variables are used to turn on/off observability of the Agent Framework:

- ENABLE_OBSERVABILITY=true
- ENABLE_SENSITIVE_DATA=true

The framework will emit observability data when the `ENABLE_OBSERVABILITY` environment variable is set to `true`. If both are `true` then it will also emit sensitive information.

> **Note**: Sensitive information includes prompts, responses, and more, and should only be enabled in a development or test environment. It is not recommended to enable this in production environments as it may expose sensitive data.

### Configuring exporters and providers

Turning on observability is just the first step, you also need to configure where to send the observability data (i.e. OTLP Endpoint, Console, Application Insights). By default, no exporters or providers are configured.

#### Setting up exporters and providers manually

Please refer to sample [advanced_manual_setup_console_output.py](./advanced_manual_setup_console_output.py) for a comprehensive example of how to manually setup exporters and providers for traces, logs, and metrics that will get sent to the console.

#### Setting up exporters and providers using `setup_observability()`

To make it easier for developers to get started, the `agent_framework.observability` module provides a `setup_observability()` function that will setup exporters and providers for traces, logs, and metrics based on environment variables. You can call this function at the start of your application to enable telemetry.

```python
from agent_framework.observability import setup_observability

setup_observability()
```

Agent Framework also has an opinionated logging format, which you can setup using:
```python
from agent_framework import setup_logging

setup_logging()
```

#### Environment variables for `setup_observability()`

The `setup_observability()` function automatically reads **standard OpenTelemetry environment variables** to configure exporters:

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

**Agent Framework Specific**:
- `ENABLE_CONSOLE_EXPORTERS` - Set to `true` to enable console output for debugging
- `ENABLE_SENSITIVE_DATA` - Set to `true` to include prompts/responses in telemetry (dev/test only)
- `ENABLE_OBSERVABILITY` - Set to `true` to enable observability (auto-enabled when `setup_observability()` is called)

> **Note**: These are standard OpenTelemetry environment variables. See the [OpenTelemetry spec](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/) for more details.

#### Three patterns for configuring observability

**1. Default Setup (Environment Variables Only)**

The simplest approach - configure everything via environment variables:

```python
from agent_framework.observability import setup_observability

# Reads OTEL_EXPORTER_OTLP_* environment variables automatically
setup_observability()
```

This is the **recommended approach** for most use cases.

**2. Custom Exporters (Programmatic Configuration)**

For advanced scenarios where you need custom exporter configuration:

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from agent_framework.observability import setup_observability

# Create custom exporters with specific configuration
exporters = [
    OTLPSpanExporter(endpoint="http://localhost:4317", compression=Compression.Gzip),
    OTLPLogExporter(endpoint="http://localhost:4317"),
    OTLPMetricExporter(endpoint="http://localhost:4317"),
]

# These will be added alongside any exporters from environment variables
setup_observability(exporters=exporters, enable_sensitive_data=True)
```

**3. Fully Custom Setup (Azure Monitor, Custom Providers)**

For complete control over telemetry providers (e.g., Azure Monitor integration):

```python
from azure.monitor.opentelemetry import configure_azure_monitor
from agent_framework.observability import create_resource, setup_observability

# Configure Azure Monitor first
configure_azure_monitor(
    connection_string="InstrumentationKey=...",
    resource=create_resource(),  # Uses OTEL_SERVICE_NAME, etc.
    enable_live_metrics=True,
)

# Then activate Agent Framework's telemetry code paths
# This is optional if ENABLE_OBSERVABILITY and or ENABLE_SENSITIVE_DATA are set in env vars
setup_observability(enable_sensitive_data=False)
```

For Azure AI projects, use the `client.setup_azure_ai_observability()` method which handles this automatically:

```python
from agent_framework.azure import AzureAIClient
from azure.ai.projects.aio import AIProjectClient

async with (
    AIProjectClient(...) as project_client,
    AzureAIClient(project_client=project_client) as client,
):
    # Automatically configures Azure Monitor with connection string from project
    await client.setup_azure_ai_observability(enable_live_metrics=True)
```
This method, first uses the project client to get the connection string from the project, it then call `configure_azure_monitor()` under the hood, and finally it calls `setup_observability()` to activate the Agent Framework telemetry code paths. The kwargs of the `setup_azure_ai_observability()` method are passed to `configure_azure_monitor()`. The `setup_observability()` method is called with `disable_exporter_creation=True` to avoid creating duplicate exporters.

> **Important**: Calling `setup_observability()` implicitly enables telemetry, even when `ENABLE_OBSERVABILITY` is set to `false` in the environment.

#### Logging
Agent Framework has a built-in logging configuration that works well with telemetry. It sets the format to a standard format that includes timestamp, pathname, line number, and log level. You can use that by calling the `setup_logging()` function from the `agent_framework` module.

```python
from agent_framework import setup_logging

setup_logging()
```
You can control at what level logging happens and thus what logs get exported, you can do this, by adding this:

```python
import logging

logger = logging.getLogger()
logger.setLevel(logging.NOTSET)
```
This gets the root logger and sets the level of that, automatically other loggers inherit from that one, and you will get detailed logs in your telemetry.

## Samples

This folder contains different samples demonstrating how to use telemetry in various scenarios.

| Sample | Description |
|--------|-------------|
| [setup_observability_with_env_var.py](./setup_observability_with_env_var.py) | **Recommended starting point**: Shows how to setup telemetry using standard OpenTelemetry environment variables (`OTEL_EXPORTER_OTLP_*`). |
| [setup_observability_with_parameters.py](./setup_observability_with_parameters.py) | Shows how to create custom exporters with specific configuration and pass them to `setup_observability()`. Useful for advanced scenarios. |
| [agent_observability.py](./agent_observability.py) | Shows telemetry collection for an agentic application with tool calls using environment variables. |
| [agent_observability_http_exporters.py](./agent_observability_http_exporters.py) | Shows how to use HTTP/protobuf OTLP exporters instead of the default gRPC exporters. Useful for backends like Langfuse. |
| [workflow_observability.py](./workflow_observability.py) | Shows telemetry collection for a workflow with multiple executors and message passing. |
| [azure_ai_agent_observability.py](./azure_ai_agent_observability.py) | Shows Azure Monitor integration using `AzureAIClient.setup_azure_ai_observability()` for Azure AI projects. |
| [azure_ai_chat_client_with_observability.py](./azure_ai_chat_client_with_observability.py) | Shows Azure Monitor integration for a chat client with an Azure AI project. |
| [advanced_manual_setup_console_output.py](./advanced_manual_setup_console_output.py) | Advanced: Shows manual setup of exporters and providers with console output. Useful for understanding how observability works under the hood. |
| [advanced_zero_code.py](./advanced_zero_code.py) | Advanced: Shows zero-code telemetry setup using the `opentelemetry-instrument` CLI tool. |

### Running the samples

1. Open a terminal and navigate to this folder: `python/samples/getting_started/observability/`. This is necessary for the `.env` file to be read correctly.
2. Create a `.env` file if one doesn't already exist in this folder. Please refer to the [example file](./.env.example).
    > **Note**: You can start with just `ENABLE_OBSERVABILITY=true` and add `OTEL_EXPORTER_OTLP_ENDPOINT` or other configuration as needed. If no exporters are configured, you can set `ENABLE_CONSOLE_EXPORTERS=true` for console output.
3. Activate your python virtual environment, and then run `python setup_observability_with_env_var.py` or others.

> Each sample will print the Operation/Trace ID, which can be used later for filtering logs and traces in Application Insights or Aspire Dashboard.

## Application Insights/Azure Monitor

### Setup with Azure AI Projects

For Azure AI projects, use the `AzureAIClient.setup_azure_ai_observability()` method which automatically retrieves the Application Insights connection string from your project:

```python
from agent_framework.azure import AzureAIClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential

async with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint="...", credential=credential) as project_client,
    AzureAIClient(project_client=project_client) as client,
):
    # Automatically configures Azure Monitor with connection string from project
    await client.setup_azure_ai_observability(
        enable_sensitive_data=True,  # dev/test only
        enable_live_metrics=True,     # passed to configure_azure_monitor()
    )

    # Now use the client for your agent operations
    response = await client.get_response(...)
```

See [azure_ai_agent_observability.py](./azure_ai_agent_observability.py) for a complete example.

### Manual Setup with Azure Monitor

For non-Azure AI projects, you can configure Azure Monitor directly:

```python
from azure.monitor.opentelemetry import configure_azure_monitor
from agent_framework.observability import create_resource, setup_observability
from azure.identity import DefaultAzureCredential

# Configure Azure Monitor with connection string and optional Entra ID auth
configure_azure_monitor(
    connection_string="InstrumentationKey=...",
    resource=create_resource(),  # Uses OTEL_SERVICE_NAME, etc.
    credential=DefaultAzureCredential(),  # Optional: for Entra ID auth
    enable_live_metrics=True,
)

# Activate Agent Framework's telemetry code paths
setup_observability(enable_sensitive_data=False)
```

It is recommended to use [DefaultAzureCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential?view=azure-python) for local development and [ManagedIdentityCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.managedidentitycredential?view=azure-python) for production environments.

### Logs and traces

Go to your Application Insights instance, click on _Transaction search_ on the left menu. Use the operation id printed by the program to search for the logs and traces associated with the operation. Click on any of the search result to view the end-to-end transaction details. Read more [here](https://learn.microsoft.com/en-us/azure/azure-monitor/app/transaction-search-and-diagnostics?tabs=transaction-search).

### Metrics

Running the application once will only generate one set of measurements (for each metrics). Run the application a couple times to generate more sets of measurements.

> Note: Make sure not to run the program too frequently. Otherwise, you may get throttled.

Please refer to here on how to analyze metrics in [Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/analyze-metrics).

### Custom Exporters and Advanced Configuration

You can create custom exporters with specific configuration and pass them to `setup_observability()`:

```python
from grpc import Compression
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from agent_framework.observability import setup_observability

# Create custom exporters with advanced configuration
exporters = [
    OTLPSpanExporter(endpoint="http://localhost:4317", compression=Compression.Gzip),
    OTLPLogExporter(endpoint="http://localhost:4317"),
    OTLPMetricExporter(endpoint="http://localhost:4317"),
]

# These will be added alongside any exporters from environment variables
setup_observability(exporters=exporters)
```

See [setup_observability_with_parameters.py](./setup_observability_with_parameters.py) for a complete example.

### Logs

When you are in Azure Monitor and want to have a overall view of the span, use this query in the logs section:

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
Besides the Application Insights native UI, you can also use Grafana to visualize the telemetry data in Application Insights. There are two tailored dashboards for you to get started quickly:

#### Agent Overview dashboard
Open dashboard in Azure portal: <https://aka.ms/amg/dash/af-agent>
![Agent Overview dashboard](https://github.com/Azure/azure-managed-grafana/raw/main/samples/assets/grafana-af-agent.gif)

#### Workflow Overview dashboard
Open dashboard in Azure portal: <https://aka.ms/amg/dash/af-workflow>
![Workflow Overview dashboard](https://github.com/Azure/azure-managed-grafana/raw/main/samples/assets/grafana-af-workflow.gif)

## Migration Guide

If you're updating from a previous version of the Agent Framework, here are the key changes to the observability API:

### Environment Variables

| Old Variable | New Variable | Notes |
|-------------|--------------|-------|
| `OTLP_ENDPOINT` | `OTEL_EXPORTER_OTLP_ENDPOINT` | Standard OpenTelemetry env var |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | N/A | Use `AzureAIClient.setup_azure_ai_observability()` |
| N/A | `ENABLE_CONSOLE_EXPORTERS` | New opt-in flag for console output |

### OTLP Configuration

**Before (Deprecated):**
```python
# Via parameter
setup_observability(otlp_endpoint="http://localhost:4317")

# Via environment variable
# OTLP_ENDPOINT=http://localhost:4317
setup_observability()
```

**After (Current):**
```python
# Via standard OTEL environment variable (recommended)
# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
setup_observability()

# Or via custom exporters
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

setup_observability(exporters=[
    OTLPSpanExporter(endpoint="http://localhost:4317"),
    OTLPLogExporter(endpoint="http://localhost:4317"),
    OTLPMetricExporter(endpoint="http://localhost:4317"),
])
```

### Azure Monitor Configuration

**Before (Deprecated):**
```python
setup_observability(
    applicationinsights_connection_string="InstrumentationKey=...",
    applicationinsights_live_metrics=True,
)
```

**After (Current):**
```python
# For Azure AI projects
from agent_framework.azure import AzureAIClient
from azure.ai.projects.aio import AIProjectClient

async with (
    AIProjectClient(...) as project_client,
    AzureAIClient(project_client=project_client) as client,
):
    await client.setup_azure_ai_observability(enable_live_metrics=True)

# For non-Azure AI projects
from azure.monitor.opentelemetry import configure_azure_monitor
from agent_framework.observability import create_resource, setup_observability

configure_azure_monitor(
    connection_string="InstrumentationKey=...",
    resource=create_resource(),
    enable_live_metrics=True,
)
setup_observability()
```

### Console Output

**Before (Deprecated):**
```python
# Console was used as automatic fallback
setup_observability()  # Would output to console if no exporters configured
```

**After (Current):**
```python
# Console exporters are now opt-in
# ENABLE_CONSOLE_EXPORTERS=true
setup_observability()

# Or programmatically
import os
os.environ["ENABLE_CONSOLE_EXPORTERS"] = "true"
setup_observability()
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
ENABLE_OBSERVABILITY=true OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 python setup_observability_with_env_var.py
```

### Viewing telemetry data

> Make sure you have the dashboard running to receive telemetry data.

Once your sample finishes running, navigate to <http://localhost:18888> in a web browser to see the telemetry data. Follow the [Aspire Dashboard exploration guide](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/explore) to authenticate to the dashboard and start exploring your traces, logs, and metrics!

## Console output

You won't have to deploy an Application Insights resource or install Docker to run Aspire Dashboard if you choose to inspect telemetry data in a console. However, it is difficult to navigate through all the spans and logs produced, so **this method is only recommended when you are just getting started**.

Use the guides from OpenTelemetry to setup exporters for [the console](https://opentelemetry.io/docs/languages/python/getting-started/), or use [advanced_manual_setup_console_output](./advanced_manual_setup_console_output.py) as a reference, just know that there are a lot of options you can setup and this is not a comprehensive example.
