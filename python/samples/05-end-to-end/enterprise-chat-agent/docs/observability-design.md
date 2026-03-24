# Observability Design — Enterprise Chat Agent

This document describes the OpenTelemetry observability design for the Enterprise Chat Agent, aligned with the Microsoft Agent Framework's built-in instrumentation.

## Design Principles

1. **Don't duplicate framework instrumentation** — Use the Agent Framework's automatic spans for agent/LLM/tool tracing
2. **Fill the gaps** — Add manual spans only for layers the framework cannot see (HTTP, Cosmos DB, validation)
3. **Use framework APIs** — Leverage `setup_observability()`, `get_tracer()`, and `get_meter()` from `agent_framework`

---

## Framework's Built-in Instrumentation (Automatic)

The Microsoft Agent Framework automatically creates these spans when you call agent/chat client methods:

| Span Name Pattern | When Created | Key Attributes |
|---|---|---|
| `invoke_agent {agent_name}` | `agent.run()` / `agent.run_stream()` | `gen_ai.agent.id`, `gen_ai.agent.name`, `gen_ai.conversation.id` |
| `chat {model_id}` | `chat_client.get_response()` / `get_streaming_response()` | `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |
| `execute_tool {function_name}` | Tool function invocations via `AIFunction` | `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.type` |

### Framework-Provided Functions

```python
from agent_framework import setup_observability, get_tracer, get_meter
```

- **`setup_observability()`** — Configures TracerProvider, MeterProvider, LoggerProvider with OTLP/Azure Monitor exporters
- **`get_tracer()`** — Returns the configured tracer for custom spans
- **`get_meter()`** — Returns the configured meter for custom metrics

### Automatic Metrics

| Metric Name | Description |
|---|---|
| `gen_ai.client.operation.duration` | Duration of LLM operations |
| `gen_ai.client.token.usage` | Token usage (input/output) |
| `agent_framework.function.invocation.duration` | Tool function execution duration |

---

## Tool vs Non-Tool Service Calls

Whether you need manual spans depends on **how** a service is invoked:

| Scenario | Manual Span Needed? | Why |
|----------|---------------------|-----|
| AI Search **as agent tool** | ❌ No | Framework creates `execute_tool` span automatically |
| Redis **as agent tool** | ❌ No | Framework creates `execute_tool` span automatically |
| AI Search **outside agent** (pre/post processing) | ✅ Yes | Framework doesn't see calls outside `agent.run()` |
| Redis **outside agent** (caching layer) | ✅ Yes | Framework doesn't see calls outside `agent.run()` |
| Cosmos DB (thread storage) | ✅ Yes | Always called outside agent context |

### Example: Tool vs Direct Call

```python
# AS A TOOL - Framework handles instrumentation automatically
@ai_function
async def search_knowledge_base(query: str) -> str:
    return await ai_search_client.search(query)  # No manual span needed

response = await agent.run(message, tools=[search_knowledge_base])
# Framework creates: invoke_agent → execute_tool search_knowledge_base

# OUTSIDE AGENT - Manual span required
async with redis_span("get", "session_cache"):
    cached_context = await redis.get(f"context:{thread_id}")  # Before agent call

async with ai_search_span("index", "conversation_logs"):
    await ai_search.index_document(log)  # After agent call for analytics
```

---

## Enterprise Chat Agent Custom Spans (Manual)

The framework doesn't know about HTTP requests, Cosmos DB operations, or services called outside the agent. We add spans for these layers:

| Layer | Span Name Pattern | Purpose |
|---|---|---|
| HTTP Request | `http.request {method} {path}` | Track request lifecycle |
| Cosmos DB | `cosmos.{operation} {container}` | Track database operations |
| Redis | `redis.{operation} {key_pattern}` | Track caching operations |
| AI Search | `ai_search.{operation} {index}` | Track search operations |
| Validation | `request.validate {operation}` | Track authorization checks |

---

## Span Hierarchy

```text
http.request POST /threads/{thread_id}/messages       ← MANUAL (HTTP layer)
├── cosmos.read threads                               ← MANUAL (Cosmos layer)
├── request.validate verify_thread_ownership          ← MANUAL (Validation)
├── invoke_agent ChatAgent                            ← FRAMEWORK (automatic)
│   ├── chat gpt-4o                                   ← FRAMEWORK (automatic)
│   │   └── (internal LLM call spans)
│   └── execute_tool get_weather                      ← FRAMEWORK (automatic)
├── cosmos.upsert threads                             ← MANUAL (Cosmos layer)
└── http.response                                     ← MANUAL (optional)
```

---

## Implementation

The observability module (`observability.py`) provides async context managers:

- **`init_observability()`** — Wraps `setup_observability()`, call once at startup
- **`http_request_span(method, path, thread_id, user_id)`** — Top-level HTTP span
- **`cosmos_span(operation, container, partition_key)`** — Cosmos DB operation span
- **`redis_span(operation, key_pattern)`** — Redis caching span
- **`ai_search_span(operation, index)`** — AI Search span
- **`validation_span(operation)`** — Request validation span

### Usage Pattern

```python
from observability import init_observability, http_request_span, cosmos_span

init_observability()  # Once at startup

@app.route(route="threads/{thread_id}/messages", methods=["POST"])
async def send_message(req: func.HttpRequest) -> func.HttpResponse:
    async with http_request_span("POST", "/threads/{thread_id}/messages", thread_id, user_id):
        async with cosmos_span("read", "threads", thread_id):
            thread = await cosmos_store.get_thread(thread_id)

        # Agent invocation - NO manual span needed (framework handles it)
        response = await agent.run(message, thread=agent_thread)

        async with cosmos_span("upsert", "threads", thread_id):
            await cosmos_store.save_thread_state(thread_id, thread)
```

---

## Dependencies

Add to `requirements.txt`:

```txt
# OpenTelemetry Core
opentelemetry-api>=1.25.0
opentelemetry-sdk>=1.25.0

# Exporters
opentelemetry-exporter-otlp>=1.25.0
azure-monitor-opentelemetry-exporter>=1.0.0b41

# Semantic Conventions
opentelemetry-semantic-conventions-ai>=0.5.0
```

---

## Environment Variables

Configure these in `local.settings.json` or Azure Function App settings:

| Variable | Description | Example |
|---|---|---|
| `ENABLE_OTEL` | Enable OpenTelemetry | `true` |
| `ENABLE_SENSITIVE_DATA` | Log message contents (dev only!) | `false` |
| `OTLP_ENDPOINT` | OTLP collector endpoint | `http://localhost:4317` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Azure Monitor connection | `InstrumentationKey=...` |
| `OTEL_SERVICE_NAME` | Service name for traces | `enterprise-chat-agent` |

### Example `local.settings.json`

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "COSMOS_ENDPOINT": "https://your-cosmos.documents.azure.com:443/",
    "COSMOS_DATABASE": "chat-database",
    "AZURE_OPENAI_ENDPOINT": "https://your-openai.openai.azure.com/",
    "AZURE_OPENAI_DEPLOYMENT": "gpt-4o",
    "ENABLE_OTEL": "true",
    "ENABLE_SENSITIVE_DATA": "false",
    "OTLP_ENDPOINT": "http://localhost:4317",
    "OTEL_SERVICE_NAME": "enterprise-chat-agent"
  }
}
```

### Azure Functions `host.json` Configuration

Enable OpenTelemetry mode for Azure Functions:

```json
{
  "version": "2.0",
  "logging": {
    "applicationInsights": {
      "samplingSettings": {
        "isEnabled": true,
        "excludedTypes": "Request"
      }
    }
  },
  "telemetryMode": "OpenTelemetry"
}
```

---

## Viewing Traces

### Local Development

Use one of these OTLP-compatible backends:

1. **Jaeger**: `docker run -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one`
2. **Aspire Dashboard**: Part of .NET Aspire, provides a nice UI
3. **AI Toolkit Extension**: Set `VS_CODE_EXTENSION_PORT` for VS Code integration

### Azure Production

Traces are sent to Azure Monitor Application Insights. View in:

1. **Azure Portal** → Application Insights → Transaction Search
2. **Azure Portal** → Application Insights → Application Map (for distributed tracing)

---

## Summary

| Layer | Span | Instrumented By |
|-------|------|-----------------|
| HTTP Request | `http.request {method} {path}` | Enterprise Agent (manual) |
| Cosmos DB | `cosmos.{operation} {container}` | Enterprise Agent (manual) |
| Validation | `request.validate {operation}` | Enterprise Agent (manual) |
| Redis (outside agent) | `redis.{operation} {key}` | Enterprise Agent (manual) |
| AI Search (outside agent) | `ai_search.{operation} {index}` | Enterprise Agent (manual) |
| Agent Invocation | `invoke_agent {name}` | Agent Framework (automatic) |
| LLM Calls | `chat {model}` | Agent Framework (automatic) |
| Tool Execution | `execute_tool {function}` | Agent Framework (automatic) |

**Key Insight**: If a service (Redis, AI Search, etc.) is invoked **as a tool** through `agent.run()`, the framework instruments it automatically. Only add manual spans for services called **outside** the agent context.
