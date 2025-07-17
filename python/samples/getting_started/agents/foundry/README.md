# Foundry Chat Client Examples

This folder contains examples demonstrating different ways to use the `FoundryChatClient` from the `agent_framework.foundry` package.

## Examples

### 1. `foundry_basic.py`
The simplest way to use FoundryChatClient. It automatically handles all configuration using environment variables.

### 2. `foundry_with_explicit_settings.py`
Shows how to explicitly configure the FoundryChatClient with custom settings, including project endpoint, model deployment, credentials, and agent name.

### 3. `foundry_with_existing_client.py`
Demonstrates how to use an existing `AIProjectClient` instance with FoundryChatClient, giving you more control over the underlying Azure AI client.

### 4. `foundry_with_existing_agent.py`
Shows how to work with a pre-existing agent by providing the agent ID to FoundryChatClient. This example also demonstrates proper cleanup of manually created agents.

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL_DEPLOYMENT_NAME`: The name of your model deployment

## Running the Examples

Each example can be run independently:

```bash
# Run the basic example
python samples/getting_started/agents/foundry/foundry_basic.py

# Run the explicit settings example
python samples/getting_started/agents/foundry/foundry_with_explicit_settings.py

# Run the existing client example
python samples/getting_started/agents/foundry/foundry_with_existing_client.py

# Run the existing agent example
python samples/getting_started/agents/foundry/foundry_with_existing_agent.py
```

All examples use the same weather tool function that returns mock weather data.
