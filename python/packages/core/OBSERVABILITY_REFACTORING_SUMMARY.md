# Observability Refactoring Summary

## Completed Changes in `agent_framework/observability.py`

### 1. ✅ Extracted `create_resource()` as Public Function

- **Location**: Lines 505-578
- **Purpose**: Create OpenTelemetry Resource from environment variables
- **Reads**: `OTEL_SERVICE_NAME`, `OTEL_SERVICE_VERSION`, `OTEL_RESOURCE_ATTRIBUTES`
- **Added to `__all__` exports**

### 2. ✅ Implemented `_get_exporters_from_env()`

- **Location**: Lines 338-502
- **Purpose**: Parse standard OpenTelemetry environment variables and create exporters
- **Supports**:
  - `OTEL_EXPORTER_OTLP_ENDPOINT`
  - `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`
  - `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`
  - `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`
  - `OTEL_EXPORTER_OTLP_PROTOCOL` (grpc/http)
  - `OTEL_EXPORTER_OTLP_HEADERS` (and signal-specific variants)
- **Features**: Graceful ImportError handling with helpful messages

### 3. ✅ Updated `ObservabilitySettings`

**Removed Fields:**
- `applicationinsights_connection_string`
- `applicationinsights_live_metrics`
- `otlp_endpoint`

**Added Fields:**
- `enable_console_exporters: bool = False` (opt-in via `ENABLE_CONSOLE_EXPORTERS`)

**Removed Methods:**
- `_configure_azure_monitor()`
- `check_connection_string_already_configured()`
- `check_endpoint_already_configured()`
- `_configure_live_metrics()`

**Updated Methods:**
- `_resource` now uses public `create_resource()` function

### 4. ✅ Simplified `_configure()` Method

**New Logic**:
1. Add exporters from environment variables (`_get_exporters_from_env()`)
2. Add passed-in exporters
3. Add console exporters if `enable_console_exporters=True`
4. Configure providers

**Removed Parameters:**
- `credential`
- `enable_console_as_fallback`

### 5. ✅ Updated `_configure_providers()`

**Removed**:
- `enable_console_as_fallback` parameter
- All fallback logic

### 6. ✅ Refactored `setup_observability()`

**Removed Parameters:**
- `otlp_endpoint`
- `applicationinsights_connection_string`
- `applicationinsights_live_metrics`
- `credential`
- `enable_console_as_fallback`

**Kept Parameters:**
- `enable_sensitive_data`
- `exporters`
- `vs_code_extension_port`
- `env_file_path`
- `env_file_encoding`

**New Behavior**:
- Automatically reads OTEL environment variables
- Console exporters are opt-in via `ENABLE_CONSOLE_EXPORTERS`
- Azure Monitor setup moved to `AzureAIClient.setup_azure_ai_observability()`

---

## Remaining Work

### 1. ⏳ Fix Tests (`tests/core/test_observability.py`)

**Issues Found:**
- Fixture references old env vars: `OTLP_ENDPOINT`, `APPLICATIONINSIGHTS_CONNECTION_STRING`
- Tests may assume console fallback behavior

**Required Changes:**
- Update `span_exporter` fixture to use new environment variables
- Remove references to removed fields
- Update test cases that relied on fallback behavior
- Update tests that used `applicationinsights_connection_string` parameter

### 2. ⏳ Update Sample Files

**Location**: `/samples/getting_started/observability/`

**Files to Update:**
1. `setup_observability_with_parameters.py` - Update to use env vars or exporters
2. `setup_observability_with_env_var.py` - Change `OTLP_ENDPOINT` to `OTEL_EXPORTER_OTLP_ENDPOINT`
3. `agent_observability.py` - Update configuration
4. `agent_observability_http_exporters.py` - Update configuration
5. `workflow_observability.py` - Update configuration
6. `advanced_manual_setup_console_output.py` - Update if needed
7. `.env.example` - Update with new environment variable names

**Files OK (No Changes):**
- `azure_ai_agent_observability.py` - Uses `AzureAIClient.setup_azure_ai_observability()`
- `azure_ai_chat_client_with_observability.py` - Uses `AzureAIClient`

### 3. ⏳ Update README.md

**Location**: `/samples/getting_started/observability/README.md`

**Required Updates:**

#### Section: "Environment variables for `setup_observability()`" (Lines 77-84)

**Replace**:
```markdown
The `setup_observability()` function will look for the following environment variables:

- OTLP_ENDPOINT="..."
- APPLICATIONINSIGHTS_CONNECTION_STRING="..."
```

**With**:
```markdown
The `setup_observability()` function automatically reads standard OpenTelemetry environment variables:

- OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
- OTEL_EXPORTER_OTLP_TRACES_ENDPOINT (optional, overrides base endpoint for traces)
- OTEL_EXPORTER_OTLP_METRICS_ENDPOINT (optional, overrides base endpoint for metrics)
- OTEL_EXPORTER_OTLP_LOGS_ENDPOINT (optional, overrides base endpoint for logs)
- OTEL_EXPORTER_OTLP_PROTOCOL="grpc" (or "http")
- OTEL_EXPORTER_OTLP_HEADERS="key1=value1,key2=value2"
- ENABLE_CONSOLE_EXPORTERS="true" (opt-in for console output)

For Azure Monitor integration, use the AzureAIClient.setup_azure_ai_observability() method.
```

#### Add Migration Guide Section (at bottom)

Add a new section before or after "Application Insights/Azure Monitor":

```markdown
## Migration Guide

### Migrating from Old Observability API

If you're updating from a previous version, here are the key changes:

#### OTLP Endpoint Configuration

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

#### Azure Monitor Configuration

**Before (Deprecated):**
```python
setup_observability(
    applicationinsights_connection_string="InstrumentationKey=...",
    applicationinsights_live_metrics=True
)
```

**After (Current):**
```python
from agent_framework.azure import AzureAIClient
from azure.ai.projects.aio import AIProjectClient

# Connection string comes from project client automatically
async with (
    AIProjectClient(...) as project_client,
    AzureAIClient(project_client=project_client) as client,
):
    await client.setup_azure_ai_observability(
        enable_live_metrics=True  # Passed to configure_azure_monitor
    )
```

#### Console Exporters

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

#### Environment Variables

| Old Variable | New Variable | Notes |
|-------------|--------------|-------|
| `OTLP_ENDPOINT` | `OTEL_EXPORTER_OTLP_ENDPOINT` | Standard OTEL env var |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | N/A | Use `AzureAIClient.setup_azure_ai_observability()` |
| `APPLICATIONINSIGHTS_LIVE_METRICS` | N/A | Pass as kwarg to Azure AI setup |
| N/A | `ENABLE_CONSOLE_EXPORTERS` | New opt-in flag |

### Benefits of New API

1. **Standards Compliant**: Uses standard OpenTelemetry environment variables
2. **Simpler**: Less configuration needed, more relies on environment
3. **Flexible**: Easy to add custom exporters alongside environment-based ones
4. **Cleaner Separation**: Azure Monitor setup is in azure-specific client
```

---

## ✅ Azure AI Client Changes (COMPLETED)

**Updated File**: `packages/azure-ai/agent_framework_azure_ai/_client.py`

The `setup_azure_ai_observability()` method has been updated:
- ✅ Uses new `create_resource()` function from core
- ✅ Calls `configure_azure_monitor()` with connection string and kwargs
- ✅ Calls `setup_observability(enable_sensitive_data=...)` to complete setup
- ✅ Proper ImportError handling with helpful message
- ✅ Updated docstring with kwargs documentation and examples
- ✅ Only exposes `enable_sensitive_data` parameter, everything else via kwargs

See `AZURE_AI_CLIENT_OBSERVABILITY_CHANGES.md` for detailed design documentation.

---

## Testing Checklist

Before marking this complete:

- [ ] All tests in `tests/core/test_observability.py` pass
- [ ] All sample files run successfully
- [ ] README.md updated with migration guide
- [ ] `.env.example` file updated
- [ ] AzureAIClient changes documented and communicated to azure-ai package maintainers
- [ ] Run mypy and lint checks
- [ ] Test with Aspire Dashboard (OTEL_EXPORTER_OTLP_ENDPOINT)
- [ ] Test with VS Code extension port
- [ ] Test console exporters flag

---

## Summary of Benefits

### For Users

1. **Standard Compliance**: Uses official OpenTelemetry environment variables
2. **Simpler Setup**: Less code needed, more configuration via environment
3. **Better Discoverability**: Standard env vars are well-documented in OTEL docs
4. **Flexibility**: Easy to mix environment config with custom exporters
5. **Cleaner API**: Azure Monitor moved to appropriate client

### For Maintainers

1. **Less Code**: Removed Azure Monitor-specific code from core
2. **Cleaner Separation**: Observability core vs Azure-specific features
3. **Easier Testing**: Standard env vars, fewer edge cases
4. **Better Aligned**: With OpenTelemetry ecosystem conventions
