# Copilot Studio Agent Examples

This folder contains examples demonstrating how to create and use agents with Microsoft Copilot Studio using the Agent Framework.

## Prerequisites

Before running these examples, you need:

1. **Copilot Studio Environment**: Access to a Microsoft Copilot Studio environment with a published copilot
2. **App Registration**: An Azure AD App Registration with appropriate permissions
3. **Environment Variables**: Set the following environment variables:
   - `COPILOTSTUDIOAGENT__ENVIRONMENTID` - Your Copilot Studio environment ID
   - `COPILOTSTUDIOAGENT__SCHEMANAME` - Your copilot's agent identifier/schema name
   - `COPILOTSTUDIOAGENT__AGENTAPPID` - Your App Registration client ID
   - `COPILOTSTUDIOAGENT__TENANTID` - Your Azure AD tenant ID

## Examples

| Example | Description |
|---------|-------------|
| **[`copilotstudio_basic.py`](copilotstudio_basic.py)** | Basic non-streaming and streaming execution with simple questions |
| **[`copilotstudio_with_explicit_settings.py`](copilotstudio_with_explicit_settings.py)** | Example with explicit settings and manual token acquisition |

## Authentication

The examples use MSAL (Microsoft Authentication Library) for authentication. The first time you run an example, you may need to complete an interactive authentication flow in your browser.

### App Registration Setup

Your Azure AD App Registration should have:

1. **API Permissions**:
   - Power Platform API permissions (https://api.powerplatform.com/.default)
   - Appropriate delegated permissions for your organization

2. **Redirect URIs**:
   - For public client flows: `http://localhost`
   - Configure as appropriate for your authentication method

3. **Authentication**:
   - Enable "Allow public client flows" if using interactive authentication

## Usage Patterns

### Basic Usage with Environment Variables

```python
import asyncio
from agent_framework.microsoft import CopilotStudioAgent

# Uses environment variables for configuration
async def main():
    # Create agent using environment variables
    agent = CopilotStudioAgent()

    # Run a simple query
    result = await agent.run("What is the capital of France?")
    print(result)

asyncio.run(main())
```

### Explicit Configuration

```python
from agent_framework.microsoft import CopilotStudioAgent, acquire_token
from microsoft_agents.copilotstudio.client import ConnectionSettings, CopilotClient, PowerPlatformCloud, AgentType

# Acquire token manually
token = acquire_token(
    client_id="your-client-id",
    tenant_id="your-tenant-id"
)

# Create settings and client
settings = ConnectionSettings(
    environment_id="your-environment-id",
    agent_identifier="your-agent-schema-name",
    cloud=PowerPlatformCloud.PROD,
    copilot_agent_type=AgentType.PUBLISHED,
    custom_power_platform_cloud=None
)

client = CopilotClient(settings=settings, token=token)
agent = CopilotStudioAgent(client=client)
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**:
   - Verify your App Registration has correct permissions
   - Ensure environment variables are set correctly
   - Check that your tenant ID and client ID are valid

2. **Environment/Agent Not Found**:
   - Verify your environment ID is correct
   - Ensure your copilot is published and the schema name is correct
   - Check that you have access to the specified environment

3. **Token Acquisition Failures**:
   - Interactive authentication may require browser access
   - Corporate firewalls may block authentication flows
   - Try running with appropriate proxy settings if needed
