# Agent Framework Python Telemetry

This sample folder shows how a Python application can be configured to send Agent Framework telemetry to the Application Performance Management (APM) vendors of your choice.

In this sample, we provide options to send telemetry to [Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview) and [Aspire Dashboard](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/overview?tabs=bash).

> **Quick Start**: For local development without Azure setup, you can use the [Aspire Dashboard](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone) which runs locally via Docker and provides an excellent telemetry viewing experience for OpenTelemetry data.

> Note that it is also possible to use other Application Performance Management (APM) vendors. An example is [Prometheus](https://prometheus.io/docs/introduction/overview/). Please refer to this [link](https://opentelemetry.io/docs/languages/python/exporters/) to learn more about exporters.

For more information, please refer to the following resources:

1. [Azure Monitor OpenTelemetry Exporter](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/monitor/azure-monitor-opentelemetry-exporter)
2. [Aspire Dashboard for Python Apps](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone-for-python?tabs=flask%2Cwindows)
3. [Python Logging](https://docs.python.org/3/library/logging.html)
4. [Observability in Python](https://www.cncf.io/blog/2022/04/22/opentelemetry-and-python-a-complete-instrumentation-guide/)

## What to expect

The Agent Framework Python SDK is designed to efficiently generate comprehensive logs, traces, and metrics throughout the flow of function execution and model invocation. This allows you to effectively monitor your AI application's performance and accurately track token consumption.

## Configuration

### Required resources

2. OpenAI or [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/create-resource?pivots=web-portal)
2. [Foundry project](https://ai.azure.com/doc/azure/ai-foundry/what-is-azure-ai-foundry)

### Optional resources

1. [Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/create-workspace-resource)
2. [Aspire Dashboard](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone-for-python?tabs=flask%2Cwindows#start-the-aspire-dashboard)

### Dependencies
No additional dependencies are required to enable telemetry. The necessary packages are included as part of the `agent-framework` package. Unless you want to use a different APM vendor, in which case you will need to install the appropriate OpenTelemetry exporter package.

### Environment variables
The following environment variables can be set to configure telemetry, the first two set the basic configuration:

- AGENT_FRAMEWORK_ENABLE_OTEL=true
- AGENT_FRAMEWORK_ENABLE_SENSITIVE_DATA=true

Next we need to know where to send the telemetry, for that you can use either a OTLP endpoint or a connection string for Application Insights:
- AGENT_FRAMEWORK_OTLP_ENDPOINT="<url to OTLP endpoint>"
or
- AGENT_FRAMEWORK_MONITOR_CONNECTION_STRING="<connection string>"
Finally, you can enable live metrics streaming to Application Insights:
- AGENT_FRAMEWORK_MONITOR_LIVE_METRICS=true

> IMPORTANT - If both OTLP endpoint and connection string are set, the connection string will take precedence and there will be no trace to the OTLP endpoint.

## Samples
This folder contains different samples demonstrating how to use telemetry in various scenarios.

### [01 - zero_code](./01-zero_code.py):
A simple example showing how to enable telemetry in a zero-touch scenario. When the above environment variables are set, telemetry will be automatically enabled, however since you do not define any overarching tracer, you will only see the spans for the specific calls to the chat client and tools.

### [02a](./02a-generic_chat_client.py) and [02b](./02b-foundry_chat_client.py) Chat Clients:
These two samples show how to first setup the telemetry by manually importing the `setup_telemetry` function from the `agent_framework.telemetry` module and calling it. After this is done, the trace that get's created will live in the same context as the chat client calls, allowing you to see the end-to-end flow of your application. For Foundry, there is a method in the Foundry project client to get the telemetry url for your project, the `.setup_foundry_telemetry()` method in the `FoundryChatClient` class will use this url to configure telemetry and you then do not have to import and call `setup_telemetry()` manually.
Because of the way OpenTelemetry works, you can only call `setup_telemetry()` once per application run, so make sure you do that in the right place.

### [03a](./03a-generic_agent.py) and [03b](./03b-foundry_agent.py) Agents:
These two samples show how to setup telemetry when using the Agent Framework's agent abstraction layer. They are similar to the chat client samples, but also show how to create an agent and invoke it. The same rules apply for setting up telemetry, you can either call `setup_telemetry()` manually, or use the `setup_foundry_telemetry()` method in the `FoundryChatClient` class.

### [04 - workflow](./04-workflow.py) Workflow:
This sample shows how to setup telemetry when using the Agent Framework's workflow execution engine. It demonstrates a simple workflow scenario with telemetry.


## Running the samples

1. Open a terminal and navigate to this folder: `python/samples/getting_started/telemetry/`. This is necessary for the `.env` file to be read correctly.
2. Create a `.env` file if one doesn't already exist in this folder. Please refer to the [example file](./.env.example).
    > Note that `CONNECTION_STRING` and `SAMPLE_OTLP_ENDPOINT` are optional. If you don't configure them, everything will get outputted to the console.
    > Set `AGENT_FRAMEWORK_ENABLE_OTEL=true` to enable basic telemetry and `AGENT_FRAMEWORK_ENABLE_SENSITIVE_DATA=true` to include sensitive information like prompts and responses.
        > Sensitive information should only be enabled in a development or test environment. It is not recommended to enable this in production environments as it may expose sensitive data.
    > Set `AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL=true` to enable workflow telemetry for the workflow samples.
3. Activate your python virtual environment, and then run `python 01-zero_code.py` or others.
> This will output the Operation/Trace ID, which can be used later for filtering.

## Application Insights/Azure Monitor

### Logs and traces

Go to your Application Insights instance, click on _Transaction search_ on the left menu. Use the operation id output by the program to search for the logs and traces associated with the operation. Click on any of the search result to view the end-to-end transaction details. Read more [here](https://learn.microsoft.com/en-us/azure/azure-monitor/app/transaction-search-and-diagnostics?tabs=transaction-search).

### Metrics

Running the application once will only generate one set of measurements (for each metrics). Run the application a couple times to generate more sets of measurements.

> Note: Make sure not to run the program too frequently. Otherwise, you may get throttled.

Please refer to here on how to analyze metrics in [Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/analyze-metrics).

## Logs

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
AGENT_FRAMEWORK_OTLP_ENDPOINT=http://localhost:4317
```

Or set it as an environment variable when running your samples:

```bash
AGENT_FRAMEWORK_ENABLE_OTEL=true AGENT_FRAMEWORK_OTLP_ENDPOINT=http://localhost:4317 python 01-zero_code.py
```

### Viewing telemetry data

> Make sure you have the dashboard running to receive telemetry data.

Once your sample finishes running, navigate to <http://localhost:18888> in a web browser to see the telemetry data. Follow the [Aspire Dashboard exploration guide](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/explore) to authenticate to the dashboard and start exploring your traces, logs, and metrics!

## Console output

You won't have to deploy an Application Insights resource or install Docker to run Aspire Dashboard if you choose to inspect telemetry data in a console. However, it is difficult to navigate through all the spans and logs produced, so **this method is only recommended when you are just getting started**.

Use the guides from OpenTelemetry to setup exporters for [the console](https://opentelemetry.io/docs/languages/python/getting-started/), or use [manual_setup_console_output](./manual_setup_console_output.py) as a reference, just know that there are a lot of options you can setup and this is not a comprehensive example.
