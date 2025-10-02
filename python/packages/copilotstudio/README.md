# Get Started with Microsoft Agent Framework Copilot Studio

Please install this package via pip:

```bash
pip install agent-framework-copilotstudio --pre
```

## Copilot Studio Agent

The Copilot Studio agent enables integration with Microsoft Copilot Studio, allowing you to interact with published copilots through the Agent Framework.

### Prerequisites

Before using the Copilot Studio agent, you need:

1. **Copilot Studio Environment**: Access to a Microsoft Copilot Studio environment with a published copilot
2. **App Registration**: An Azure AD App Registration with appropriate permissions for Power Platform API
3. **Environment Configuration**: Set the required environment variables or pass them as parameters

### Environment Variables

The following environment variables are used for configuration:

- `COPILOTSTUDIOAGENT__ENVIRONMENTID` - Your Copilot Studio environment ID
- `COPILOTSTUDIOAGENT__SCHEMANAME` - Your copilot's agent identifier/schema name
- `COPILOTSTUDIOAGENT__AGENTAPPID` - Your App Registration client ID
- `COPILOTSTUDIOAGENT__TENANTID` - Your Azure AD tenant ID

### Basic Usage Example

```python
import asyncio
from agent_framework.microsoft import CopilotStudioAgent

async def main():
    # Create agent using environment variables
    agent = CopilotStudioAgent()

    # Run a simple query
    result = await agent.run("What is the capital of France?")
    print(result)

asyncio.run(main())
```

### Explicit Configuration Example

```python
import asyncio
import os
from agent_framework.microsoft import CopilotStudioAgent, acquire_token
from microsoft_agents.copilotstudio.client import ConnectionSettings, CopilotClient, PowerPlatformCloud, AgentType

async def main():
    # Acquire authentication token
    token = acquire_token(
        client_id=os.environ["COPILOTSTUDIOAGENT__AGENTAPPID"],
        tenant_id=os.environ["COPILOTSTUDIOAGENT__TENANTID"]
    )

    # Create connection settings
    settings = ConnectionSettings(
        environment_id=os.environ["COPILOTSTUDIOAGENT__ENVIRONMENTID"],
        agent_identifier=os.environ["COPILOTSTUDIOAGENT__SCHEMANAME"],
        cloud=PowerPlatformCloud.PROD,
        copilot_agent_type=AgentType.PUBLISHED,
        custom_power_platform_cloud=None
    )

    # Create client and agent
    client = CopilotClient(settings=settings, token=token)
    agent = CopilotStudioAgent(client=client)

    # Run a query
    result = await agent.run("What is the capital of Italy?")
    print(result)

asyncio.run(main())
```

### Authentication

The package uses MSAL (Microsoft Authentication Library) for authentication with interactive flows when needed. Ensure your App Registration has:

- **API Permissions**: Power Platform API permissions (https://api.powerplatform.com/.default)
- **Redirect URIs**: Configured appropriately for your authentication method
- **Public Client Flows**: Enabled if using interactive authentication

### Examples

For more comprehensive examples, see the [Copilot Studio examples](https://github.com/microsoft/agent-framework/tree/main/python/samples/getting_started/agents/copilotstudio/) which demonstrate:

- Basic non-streaming and streaming execution
- Explicit settings and manual token acquisition
- Different authentication patterns
- Error handling and troubleshooting
