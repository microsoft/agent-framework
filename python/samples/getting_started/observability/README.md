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

- ENABLE_OTEL=true
- ENABLE_SENSITIVE_DATA=true

The framework will emit observability data when one of the above environment variables is set to true.

> **Note**: Sensitive information includes prompts, responses, and more, and should only be enabled in a development or test environment. It is not recommended to enable this in production environments as it may expose sensitive data.

### Configuring exporters and providers

Turning on observability is just the first step, you also need to configure where to send the observability data (i.e. Console, Application Insights). By default, no exporters or providers are configured.

#### Setting up exporters and providers manually

Please refer to sample [advanced_manual_setup_console_output.py](./advanced_manual_setup_console_output.py) for a comprehensive example of how to manually setup exporters and providers for traces, logs, and metrics that will get sent to the console.

#### Setting up exporters and providers using `setup_observability()`

To make it easier for developers to get started, the `agent_framework.observability` module provides a `setup_observability()` function that will setup exporters and providers for traces, logs, and metrics based on environment variables. You can call this function at the start of your application to enable telemetry.

```python
from agent_framework.observability import setup_observability

setup_observability()
```

#### Environment variables for `setup_observability()`

The `setup_observability()` function will look for the following environment variables to determine how to setup the exporters and providers:

- OTLP_ENDPOINT="..."
- APPLICATIONINSIGHTS_CONNECTION_STRING="..."

By providing the above environment variables, the `setup_observability()` function will automatically configure the appropriate exporters and providers for you. If no environment variables are provided, the function will not setup any exporters or providers.

You can also pass in a list of exporters directly to the `setup_observability()` function if you want to customize the exporters or add additional ones besides the ones configured via environment variables.

```python
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from agent_framework.observability import setup_observability

exporter = OTLPSpanExporter(endpoint="another-otlp-endpoint")
setup_observability(exporters=[exporter])
```

> Using this method implicitly enables telemetry, so you do not need to set the `ENABLE_OTEL` environment variable. You can still set `ENABLE_SENSITIVE_DATA` to control whether sensitive data is included in the telemetry, or call the `setup_observability()` function with the `enable_sensitive_data` parameter set to `True`.

#### Logging
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
| [setup_observability_with_parameters.py](./setup_observability_with_parameters.py) | A simple example showing how to setup telemetry by passing in parameters to the `setup_observability()` function. |
| [setup_observability_with_env_var.py](./setup_observability_with_env_var.py) | A simple example showing how to setup telemetry with the `setup_observability()` function using environment variables. |
| [agent_observability.py](./agent_observability.py) | A simple example showing how to setup telemetry for an agentic application. |
| [azure_ai_agent_observability.py](./azure_ai_agent_observability.py) | A simple example showing how to setup telemetry for an agentic application with an Azure AI project. |
| [azure_ai_chat_client_with_observability.py](./azure_ai_chat_client_with_observability.py) | A simple example showing how to setup telemetry for a chat client with an Azure AI project. |
| [workflow_observability.py](./workflow_observability.py) | A simple example showing how to setup telemetry for a workflow. |
| [advanced_manual_setup_console_output.py](./advanced_manual_setup_console_output.py) | A comprehensive example showing how to manually setup exporters and providers for traces, logs, and metrics that will get sent to the console. |
| [advanced_zero_code.py](./advanced_zero_code.py) | A comprehensive example showing how to setup telemetry using the `opentelemetry-instrument` lib without modifying any code. |

### Running the samples

1. Open a terminal and navigate to this folder: `python/samples/getting_started/observability/`. This is necessary for the `.env` file to be read correctly.
2. Create a `.env` file if one doesn't already exist in this folder. Please refer to the [example file](./.env.example).
    > Note that `APPLICATIONINSIGHTS_CONNECTION_STRING` and `OTLP_ENDPOINT` are optional. If you don't configure them, everything will get outputted to the console.
3. Activate your python virtual environment, and then run `python setup_observability_with_env_vars.py` or others.

> This will also print the Operation/Trace ID, which can be used later for filtering logs and traces in Application Insights or Aspire Dashboard.

## Application Insights/Azure Monitor

### Authentication

You can connect to your Application Insights instance using a connection string. You can also authenticate using Entra ID by passing a [TokenCredential](https://learn.microsoft.com/en-us/python/api/azure-core/azure.core.credentials.tokencredential?view=azure-python) to the `setup_observability()` function used in the samples above.

```python
from azure.identity import DefaultAzureCredential

# The credential will be for resources specified in the environment variables and the parameters passed in.
setup_observability(..., credential=DefaultAzureCredential())
```

It is recommended to use [DefaultAzureCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential?view=azure-python) for local development and [ManagedIdentityCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.managedidentitycredential?view=azure-python) for production environments.

### Logs and traces

Go to your Application Insights instance, click on _Transaction search_ on the left menu. Use the operation id printed by the program to search for the logs and traces associated with the operation. Click on any of the search result to view the end-to-end transaction details. Read more [here](https://learn.microsoft.com/en-us/azure/azure-monitor/app/transaction-search-and-diagnostics?tabs=transaction-search).

### Metrics

Running the application once will only generate one set of measurements (for each metrics). Run the application a couple times to generate more sets of measurements.

> Note: Make sure not to run the program too frequently. Otherwise, you may get throttled.

Please refer to here on how to analyze metrics in [Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/analyze-metrics).

### Adding exporters

You can also create exporters directly and have those added to the tracer_providers, logger_providers and metrics_providers, this is useful if you want to add a different exporter on the fly, or if you want to customize the exporter. Here is an example of how to create an OTLP exporter and add it to the observability setup:

```python
from grpc import Compression
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from agent_framework.observability import setup_observability

exporter = OTLPSpanExporter(endpoint="your-otlp-endpoint", compression=Compression.Gzip)
setup_observability(exporters=[exporter])
```

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
OTLP_ENDPOINT=http://localhost:4317
```

Or set it as an environment variable when running your samples:

```bash
ENABLE_OTEL=true OTLP_ENDPOINT=http://localhost:4317 python 01-zero_code.py
```

### Viewing telemetry data

> Make sure you have the dashboard running to receive telemetry data.

Once your sample finishes running, navigate to <http://localhost:18888> in a web browser to see the telemetry data. Follow the [Aspire Dashboard exploration guide](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/explore) to authenticate to the dashboard and start exploring your traces, logs, and metrics!

## Console output

You won't have to deploy an Application Insights resource or install Docker to run Aspire Dashboard if you choose to inspect telemetry data in a console. However, it is difficult to navigate through all the spans and logs produced, so **this method is only recommended when you are just getting started**.

Use the guides from OpenTelemetry to setup exporters for [the console](https://opentelemetry.io/docs/languages/python/getting-started/), or use [advanced_manual_setup_console_output](./advanced_manual_setup_console_output.py) as a reference, just know that there are a lot of options you can setup and this is not a comprehensive example.
