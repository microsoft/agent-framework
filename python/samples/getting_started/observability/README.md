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

Next to what happens in the code when you run, we also make setting up observability as easy as possible. By calling a single function `configure_otel_providers()` from the `agent_framework.observability` module, you can enable telemetry for traces, logs, and metrics. The function automatically reads standard OpenTelemetry environment variables to configure exporters and providers, making it simple to get started.

### Five patterns for configuring observability

We've identified multiple ways to configure observability in your application, depending on your needs:

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
# Enable console exporters via environment variable

configure_otel_providers(enable_console_exporters=True)
```
This is the **recommended approach** for getting started.

**2. Custom Exporters**
One level more control over the exporters that are created is to do that yourself, and then pass them to `configure_otel_providers()`. We will still create the providers for you, but you can customize the exporters as needed:

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from agent_framework.observability import configure_otel_providers

# Create custom exporters with specific configuration
exporters = [
    OTLPSpanExporter(endpoint="http://localhost:4317", compression=Compression.Gzip),
    OTLPLogExporter(endpoint="http://localhost:4317"),
    OTLPMetricExporter(endpoint="http://localhost:4317"),
]

# These will be added alongside any exporters from environment variables
configure_otel_providers(exporters=exporters, enable_sensitive_data=True)
```

**3. Third party setup**

A lot of third party specific otel package, have their own easy setup methods, for example Azure Monitor has `configure_azure_monitor()`. You can use those methods to setup the third party first, and then call `enable_instrumentation()` from the `agent_framework.observability` module to activate the Agent Framework telemetry code paths. In all these cases, if you already setup observability via environment variables, you don't need to call `enable_instrumentation()` as it will be enabled automatically.

```python
from azure.monitor.opentelemetry import configure_azure_monitor
from agent_framework.observability import create_resource, enable_instrumentation

# Configure Azure Monitor first
configure_azure_monitor(
    connection_string="InstrumentationKey=...",
    resource=create_resource(),  # Uses OTEL_SERVICE_NAME, etc.
    enable_live_metrics=True,
)

# Then activate Agent Framework's telemetry code paths
# This is optional if ENABLE_INSTRUMENTATION and or ENABLE_SENSITIVE_DATA are set in env vars
enable_instrumentation(enable_sensitive_data=False)
```
For Azure AI projects, use the `client.configure_azure_monitor()` method which wraps the calls to `configure_azure_monitor()` and `enable_instrumentation()`:

```python
from agent_framework.azure import AzureAIClient
from azure.ai.projects.aio import AIProjectClient

async with (
    AIProjectClient(...) as project_client,
    AzureAIClient(project_client=project_client) as client,
):
    # Automatically configures Azure Monitor with connection string from project
    await client.configure_azure_monitor(enable_live_metrics=True)
```

Or with [Langfuse](https://langfuse.com/integrations/frameworks/microsoft-agent-framework):

```python
# environment should be setup correctly, with langfuse urls and keys
from agent_framework.observability import enable_instrumentation
from langfuse import get_client

langfuse = get_client()

# Verify connection
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")

# Then activate Agent Framework's telemetry code paths
# This is optional if ENABLE_INSTRUMENTATION and or ENABLE_SENSITIVE_DATA are set in env vars
enable_instrumentation(enable_sensitive_data=False)
```

**4. Manual setup**
Of course you can also do a complete manual setup of exporters, providers, and instrumentation. Please refer to sample [advanced_manual_setup_console_output.py](./advanced_manual_setup_console_output.py) for a comprehensive example of how to manually setup exporters and providers for traces, logs, and metrics that will get sent to the console. This gives you full control over which exporters and providers to use. We do have a helper function `create_resource()` in the `agent_framework.observability` module that you can use to create a resource with the appropriate service name and version based on environment variables or standard defaults for Agent Framework, this is not used in the sample.

**5. Auto-instrumentation (zero-code)**
You can also use the [OpenTelemetry CLI tool](https://opentelemetry.io/docs/instrumentation/python/getting-started/#automatic-instrumentation) to automatically instrument your application without changing any code. Please refer to sample [advanced_zero_code.py](./advanced_zero_code.py) for an example of how to use the CLI tool to enable instrumentation for Agent Framework applications.

## Configuration

### Dependencies

As part of Agent Framework we use the following OpenTelemetry packages:
- `opentelemetry-api`
- `opentelemetry-sdk`
- `opentelemetry-semantic-conventions-ai`

We do not install exporters by default, so you will need to add those yourself, this prevents us from installing unnecessary dependencies. For Application Insights, you will need to install `azure-monitor-opentelemetry`. For Aspire Dashboard or other OTLP compatible backends, you will need to install `opentelemetry-exporter-otlp-proto-grpc`. For HTTP protocol support, you will also need to install `opentelemetry-exporter-otlp-proto-http`.

And for many others, different packages are used, so refer to the documentation of the specific exporter you want to use.

### Environment variables

The following environment variables are used to turn on/off observability of the Agent Framework:

- `ENABLE_INSTRUMENTATION`
- `ENABLE_SENSITIVE_DATA`
- `ENABLE_CONSOLE_EXPORTERS`

All of these are booleans and default to `false`.

Finally we have `VS_CODE_EXTENSION_PORT` which you can set to a port, which can be used to setup the AI Toolkit for VS Code tracing integration. See [here](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio#tracing) for more details.

The framework will emit observability data when the `ENABLE_INSTRUMENTATION` environment variable is set to `true`. If both are `true` then it will also emit sensitive information. When these are not set, or set to false, you can use the `enable_instrumentation()` function from the `agent_framework.observability` module to turn on instrumentation programmatically. This is useful when you want to control this via code instead of environment variables.

> **Note**: Sensitive information includes prompts, responses, and more, and should only be enabled in a development or test environment. It is not recommended to enable this in production environments as it may expose sensitive data.

The two other variables, `ENABLE_CONSOLE_EXPORTERS` and `VS_CODE_EXTENSION_PORT`, are used to configure where the observability data is sent. Those are only activated when calling `configure_otel_providers()`.

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
| [configure_otel_providers_with_parameters.py](./configure_otel_providers_with_parameters.py) | **Recommended starting point**: Shows how to create custom exporters with specific configuration and pass them to `configure_otel_providers()`. Useful for advanced scenarios. |
| [configure_otel_providers_with_env_var.py](./configure_otel_providers_with_env_var.py) | Shows how to setup telemetry using standard OpenTelemetry environment variables (`OTEL_EXPORTER_OTLP_*`). |
| [agent_observability.py](./agent_observability.py) | Shows telemetry collection for an agentic application with tool calls using environment variables. |
| [agent_with_foundry_tracing.py](./agent_with_foundry_tracing.py) | Shows Azure Monitor integration with Foundry for any chat client. |
| [azure_ai_agent_observability.py](./azure_ai_agent_observability.py) | Shows Azure Monitor integration for a AzureAIClient. |
| [advanced_manual_setup_console_output.py](./advanced_manual_setup_console_output.py) | Advanced: Shows manual setup of exporters and providers with console output. Useful for understanding how observability works under the hood. |
| [advanced_zero_code.py](./advanced_zero_code.py) | Advanced: Shows zero-code telemetry setup using the `opentelemetry-enable_instrumentation` CLI tool. |
| [workflow_observability.py](./workflow_observability.py) | Shows telemetry collection for a workflow with multiple executors and message passing. |

### Running the samples

1. Open a terminal and navigate to this folder: `python/samples/getting_started/observability/`. This is necessary for the `.env` file to be read correctly.
2. Create a `.env` file if one doesn't already exist in this folder. Please refer to the [example file](./.env.example).
    > **Note**: You can start with just `ENABLE_INSTRUMENTATION=true` and add `OTEL_EXPORTER_OTLP_ENDPOINT` or other configuration as needed. If no exporters are configured, you can set `ENABLE_CONSOLE_EXPORTERS=true` for console output.
3. Activate your python virtual environment, and then run `python configure_otel_providers_with_env_var.py` or others.

> Each sample will print the Operation/Trace ID, which can be used later for filtering logs and traces in Application Insights or Aspire Dashboard.

# Appendix

## Azure Monitor Queries

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

We've done a major update to the observability API in Agent Framework Python SDK. The new API simplifies configuration by relying more on standard OpenTelemetry environment variables and have split the instrumentation from the configuration.

If you're updating from a previous version of the Agent Framework, here are the key changes to the observability API:

### Environment Variables

| Old Variable | New Variable | Notes |
|-------------|--------------|-------|
| `OTLP_ENDPOINT` | `OTEL_EXPORTER_OTLP_ENDPOINT` | Standard OpenTelemetry env var |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | N/A | Use `configure_azure_monitor()` |
| N/A | `ENABLE_CONSOLE_EXPORTERS` | New opt-in flag for console output |

### OTLP Configuration

**Before (Deprecated):**
```python
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
```python
from agent_framework.observability import setup_observability

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
    await client.configure_azure_monitor(enable_live_metrics=True)

# For non-Azure AI projects
from azure.monitor.opentelemetry import configure_azure_monitor
from agent_framework.observability import create_resource, enable_instrumentation

configure_azure_monitor(
    connection_string="InstrumentationKey=...",
    resource=create_resource(),
    enable_live_metrics=True,
)
enable_instrumentation()
```

### Console Output

**Before (Deprecated):**
```python
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
ENABLE_INSTRUMENTATION=true OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 python configure_otel_providers_with_env_var.py
```

### Viewing telemetry data

> Make sure you have the dashboard running to receive telemetry data.

Once your sample finishes running, navigate to <http://localhost:18888> in a web browser to see the telemetry data. Follow the [Aspire Dashboard exploration guide](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/explore) to authenticate to the dashboard and start exploring your traces, logs, and metrics!
