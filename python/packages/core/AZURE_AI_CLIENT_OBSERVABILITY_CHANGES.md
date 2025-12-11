# Azure AIClient Observability Changes

## Overview

The `AzureAIClient.setup_azure_ai_observability()` method in the `agent-framework-azure-ai` package needs to be updated to work with the new observability API.

## Required Changes

### Update setup_azure_ai_observability() implementation

The method should:
1. Use the new public `create_resource()` function from core
2. Call `configure_azure_monitor()` with the connection string from the project client
3. Call core's `setup_observability()` to complete the setup

### New Implementation

```python
async def setup_azure_ai_observability(
    self,
    *,
    enable_sensitive_data: bool = False,
    **kwargs: Any
) -> None:
    """Setup observability with Azure Monitor (Azure AI Foundry integration).

    This method configures Azure Monitor for telemetry collection using the
    connection string from the Azure AI project client.

    Args:
        enable_sensitive_data: Enable sensitive data logging (prompts, responses).
            Should only be enabled in development/test environments. Default is False.
        **kwargs: Additional arguments passed to configure_azure_monitor().
            Common options include:
            - enable_live_metrics (bool): Enable Azure Monitor Live Metrics
            - credential (TokenCredential): Azure credential for Entra ID auth
            - resource (Resource): Custom OpenTelemetry resource
            See https://learn.microsoft.com/python/api/azure-monitor-opentelemetry/azure.monitor.opentelemetry.configure_azure_monitor
            for full list of options.

    Raises:
        ImportError: If azure-monitor-opentelemetry is not installed.

    Examples:
        .. code-block:: python

            from agent_framework.azure import AzureAIClient
            from azure.ai.projects.aio import AIProjectClient
            from azure.identity.aio import DefaultAzureCredential

            async with (
                DefaultAzureCredential() as credential,
                AIProjectClient(
                    endpoint="https://your-project.api.azureml.ms",
                    credential=credential
                ) as project_client,
                AzureAIClient(project_client=project_client) as client,
            ):
                # Setup observability with defaults
                await client.setup_azure_ai_observability()

                # With live metrics enabled
                await client.setup_azure_ai_observability(
                    enable_live_metrics=True
                )

                # With sensitive data logging (dev/test only)
                await client.setup_azure_ai_observability(
                    enable_sensitive_data=True
                )

    Note:
        This method retrieves the Application Insights connection string from the
        Azure AI project client automatically. You must have Application Insights
        configured in your Azure AI project for this to work.
    """
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError as exc:
        raise ImportError(
            "azure-monitor-opentelemetry is required for Azure Monitor integration. "
            "Install it with: pip install azure-monitor-opentelemetry"
        ) from exc

    from agent_framework.observability import create_resource, setup_observability

    # Get connection string from project client
    connection_string = await self._get_connection_string()  # or however you get it

    # Create resource if not provided in kwargs
    if "resource" not in kwargs:
        kwargs["resource"] = create_resource()

    # Configure Azure Monitor
    configure_azure_monitor(
        connection_string=connection_string,
        **kwargs
    )

    # Complete setup with core observability
    setup_observability(enable_sensitive_data=enable_sensitive_data)
```

### Key Points

1. **Import Error Handling**: Azure Monitor packages are optional, so wrap the import in try/except
2. **Resource Creation**: Use `create_resource()` from core if not provided in kwargs
3. **Docstring**: Document that kwargs are passed to `configure_azure_monitor()` so users can look up options there
4. **Only expose enable_sensitive_data**: This is the main setting users need, everything else goes through kwargs

### Migration for Users

Users who were calling setup_observability() with Azure Monitor settings directly should now use AzureAIClient.setup_azure_ai_observability():

**Before:**
```python
from agent_framework import setup_observability

setup_observability(
    applicationinsights_connection_string="InstrumentationKey=...",
    applicationinsights_live_metrics=True
)
```

**After:**
```python
from agent_framework.azure import AzureAIClient

# Connection string comes from project client automatically
await client.setup_azure_ai_observability(
    enable_live_metrics=True  # Passed via kwargs to configure_azure_monitor
)
```

## Testing

Ensure tests cover:
- Basic setup without options
- Setup with enable_live_metrics
- Setup with enable_sensitive_data
- Setup with custom resource
- Setup with Entra ID credential
- Error handling when azure-monitor-opentelemetry not installed
