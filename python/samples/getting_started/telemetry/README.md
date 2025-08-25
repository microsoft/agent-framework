# Agent Framework Python Telemetry

This sample project shows how a Python application can be configured to send Agent Framework telemetry to the Application Performance Management (APM) vendors of your choice.

In this sample, we provide options to send telemetry to [Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview), [Aspire Dashboard](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/overview?tabs=bash), and console output.

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

### Optional resources

1. [Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/create-workspace-resource)
2. [Aspire Dashboard](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/standalone-for-python?tabs=flask%2Cwindows#start-the-aspire-dashboard)

### Dependencies

You will also need to install the following dependencies to your virtual environment to run this sample:

```bash
# For Azure ApplicationInsights/AzureMonitor
uv pip install azure-monitor-opentelemetry azure-monitor-opentelemetry-exporter
# For OTLP endpoint
uv pip install opentelemetry-exporter-otlp-proto-grpc
```

## Running the sample

1. Open a terminal and navigate to this folder: `python/samples/getting_started/telemetry/`. This is necessary for the `.env` file to be read correctly.
2. Create a `.env` file if one doesn't already exist in this folder. Please refer to the [example file](./.env.example).
    > Note that `CONNECTION_STRING` and `SAMPLE_OTLP_ENDPOINT` are optional. If you don't configure them, everything will get outputted to the console.
    > Set `AGENT_FRAMEWORK_GENAI_ENABLE_OTEL_DIAGNOSTICS=true` to enable basic telemetry and `AGENT_FRAMEWORK_GENAI_ENABLE_OTEL_DIAGNOSTICS_SENSITIVE=true` to include sensitive information like prompts and responses.
    > Set `AGENT_FRAMEWORK_WORKFLOW_ENABLE_OTEL_DIAGNOSTICS=true` to enable workflow telemetry for the workflow samples.
        > Sensitive information should only be enabled in a development or test environment. It is not recommended to enable this in production environments as it may expose sensitive data.
3. Activate your python virtual environment, and then run `python scenarios.py`, `python interactive.py`, `python agent.py`, or `python workflow.py`.

> This will output the Operation/Trace ID, which can be used later for filtering.

### Scenarios

This sample includes multiple applications demonstrating Agent Framework telemetry:

#### scenarios.py

Organized into specific scenarios where the framework will generate useful telemetry data:

- `chat_client`: This is when a chat client is invoked directly (i.e. not streaming) with a weather tool function. **Information about the call to the underlying model and tool usage will be recorded**.
- `chat_client_stream`: This is when a chat client is invoked with streaming enabled and a weather tool function. **Information about the streaming call to the underlying model and tool usage will be recorded**.
- `ai_function`: This is when an AI function (`get_weather`) is invoked directly. **Information about the AI function and the call to the underlying model will be recorded**.

By default, running `python scenarios.py` will run all three scenarios. To run individual scenarios, use the `--scenario` command line argument. For example, `python scenarios.py --scenario chat_client`. For more information, please run `python scenarios.py -h`.

#### interactive.py

An interactive chat application that demonstrates telemetry collection in a conversational context. This sample includes the same `get_weather` tool function and allows for multi-turn conversations. Run `python interactive.py` and start chatting. Type 'exit' to quit the application. This sample only logs at the `WARNING` level, so you will not see as much telemetry data as in the `scenarios.py` sample.

#### agent.py

A sample demonstrating Agent Framework telemetry collection for agent-based workflows. This shows how telemetry is captured when using the Agent Framework's agent abstraction layer, including agent initialization, message processing, and tool execution within an agent context.

By default, running `python agent.py` will run all agent scenarios. To run individual scenarios, use the `--scenario` command line argument. For example, `python agent.py --scenario basic`. For more information, please run `python agent.py -h`.

#### workflow.py

A sample demonstrating workflow telemetry collection for the Agent Framework's workflow execution engine. This includes two scenarios:

- `sequential`: A simple sequential workflow that processes text through two connected executors (uppercase conversion followed by text reversal). **Information about workflow execution, executor processing, and message passing between executors will be recorded**.
- `sub_workflow`: A more complex scenario demonstrating sub-workflow patterns with a parent workflow orchestrating multiple text processing tasks via sub-workflows. **Information about parent workflow execution, sub-workflow invocation, and cross-workflow communication will be recorded**.

By default, running `python workflow.py` will run all workflow scenarios. To run individual scenarios, use the `--scenario` command line argument. For example, `python workflow.py --scenario sequential`. For more information, please run `python workflow.py -h`.

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
OTLP_ENDPOINT=http://localhost:4317
```

Or set it as an environment variable when running your samples:

```bash
OTLP_ENDPOINT=http://localhost:4317 python scenarios.py
```

### Viewing telemetry data

> Make sure you have the dashboard running to receive telemetry data.

Once your sample finishes running, navigate to <http://localhost:18888> in a web browser to see the telemetry data. Follow the [Aspire Dashboard exploration guide](https://learn.microsoft.com/en-us/dotnet/aspire/fundamentals/dashboard/explore) to authenticate to the dashboard and start exploring your traces, logs, and metrics!

## Console output

You won't have to deploy an Application Insights resource or install Docker to run Aspire Dashboard if you choose to inspect telemetry data in a console. However, it is difficult to navigate through all the spans and logs produced, so **this method is only recommended when you are just getting started**.

We recommend you to get started with the `chat_client` scenario as this generates the least amount of telemetry data. Below is similar to what you will see when you run `python scenarios.py --scenario chat_client`:

```Json
{
    "name": "chat.completions gpt-4o",
    "context": {
        "trace_id": "0xbda1d9efcd65435653d18fa37aef7dd3",
        "span_id": "0xcd443e1917510385",
        "trace_state": "[]"
    },
    "kind": "SpanKind.INTERNAL",
    "parent_id": "0xeca0a2ca7b7a8191",
    "start_time": "2024-09-09T23:13:14.625156Z",
    "end_time": "2024-09-09T23:13:17.311909Z",
    "status": {
        "status_code": "UNSET"
    },
    "attributes": {
        "gen_ai.operation.name": "chat.completions",
        "gen_ai.system": "openai",
        "gen_ai.request.model": "gpt-4o",
        "gen_ai.response.id": "chatcmpl-A5hrG13nhtFsOgx4ziuoskjNscHtT",
        "gen_ai.response.finish_reason": "FinishReason.STOP",
        "gen_ai.response.prompt_tokens": 16,
        "gen_ai.response.completion_tokens": 28
    },
    "events": [
        {
            "name": "gen_ai.content.prompt",
            "timestamp": "2024-09-09T23:13:14.625156Z",
            "attributes": {
                "gen_ai.prompt": "[{\"role\": \"user\", \"content\": \"Why is the sky blue in one sentence?\"}]"
            }
        },
        {
            "name": "gen_ai.content.completion",
            "timestamp": "2024-09-09T23:13:17.311909Z",
            "attributes": {
                "gen_ai.completion": "[{\"role\": \"assistant\", \"content\": \"The sky appears blue because molecules in the Earth's atmosphere scatter shorter wavelengths of sunlight, such as blue, more effectively than longer wavelengths like red.\"}]"
            }
        }
    ],
    "links": [],
    "resource": {
        "attributes": {
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.version": "1.26.0",
            "service.name": "TelemetryExample"
        },
        "schema_url": ""
    }
}
{
    "name": "Scenario: Chat Client",
    "context": {
        "trace_id": "0xbda1d9efcd65435653d18fa37aef7dd3",
        "span_id": "0xeca0a2ca7b7a8191",
        "trace_state": "[]"
    },
    "kind": "SpanKind.INTERNAL",
    "parent_id": "0x48af7ad55f2f64b5",
    "start_time": "2024-09-09T23:13:14.625156Z",
    "end_time": "2024-09-09T23:13:17.312910Z",
    "status": {
        "status_code": "UNSET"
    },
    "attributes": {},
    "events": [],
    "links": [],
    "resource": {
        "attributes": {
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.version": "1.26.0",
            "service.name": "TelemetryExample"
        },
        "schema_url": ""
    }
}
{
    "name": "Scenario's",
    "context": {
        "trace_id": "0xbda1d9efcd65435653d18fa37aef7dd3",
        "span_id": "0x48af7ad55f2f64b5",
        "trace_state": "[]"
    },
    "kind": "SpanKind.INTERNAL",
    "parent_id": null,
    "start_time": "2024-09-09T23:13:13.840481Z",
    "end_time": "2024-09-09T23:13:17.312910Z",
    "status": {
        "status_code": "UNSET"
    },
    "attributes": {},
    "events": [],
    "links": [],
    "resource": {
        "attributes": {
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.version": "1.26.0",
            "service.name": "TelemetryExample"
        },
        "schema_url": ""
    }
}
{
    "body": "Agent Framework usage: CompletionUsage(completion_tokens=28, prompt_tokens=16, total_tokens=44)",
    "severity_number": "<SeverityNumber.INFO: 9>",
    "severity_text": "INFO",
    "attributes": {
        "code.filepath": "/path/to/agent_framework/openai/chat_client.py",
        "code.function": "store_usage",
        "code.lineno": 81
    },
    "dropped_attributes": 0,
    "timestamp": "2024-09-09T23:13:17.311909Z",
    "observed_timestamp": "2024-09-09T23:13:17.311909Z",
    "trace_id": "0xbda1d9efcd65435653d18fa37aef7dd3",
    "span_id": "0xcd443e1917510385",
    "trace_flags": 1,
    "resource": {
        "attributes": {
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.version": "1.26.0",
            "service.name": "TelemetryExample"
        },
        "schema_url": ""
    }
}
```

In the output, you will find three spans: `Scenario's`, `Scenario: Chat Client`, and `chat.completions gpt-4o`, each representing a different layer in the sample. In particular, `chat.completions gpt-4o` is generated by the chat client. Inside it, you will find information about the call, such as the timestamp of the operation, the response id and the finish reason. You will also find sensitive information such as the prompt and response to and from the model (only if you have `AGENT_FRAMEWORK__GENAI_ENABLE_OTEL_DIAGNOSTICS_SENSITIVE` set to true). If you use Application Insights or Aspire Dashboard, these information will be available to you in an interactive UI.
