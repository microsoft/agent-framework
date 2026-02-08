# DevUI Samples

This folder contains sample agents and workflows designed to work with the Agent Framework DevUI - a lightweight web interface for running and testing agents interactively.

## What is DevUI?

DevUI is a sample application that provides:

- A web interface for testing agents and workflows
- OpenAI-compatible API endpoints
- Directory-based entity discovery
- In-memory entity registration
- Sample entity gallery

> **Note**: DevUI is a sample app for development and testing. For production use, build your own custom interface using the Agent Framework SDK.

## Quick Start

### Option 1: In-Memory Mode (Simplest)

Run a single sample directly. This demonstrates how to wrap agents and workflows programmatically without needing a directory structure:

```bash
cd python/samples/getting_started/devui
python in_memory_mode.py
```

This opens your browser at http://localhost:8090 with pre-configured agents and a basic workflow.

### Option 2: Directory Discovery

Launch DevUI to discover all samples in this folder:

```bash
cd python/samples/getting_started/devui
devui
```

This starts the server at http://localhost:8080 with all agents and workflows available.

## Sample Structure

Each agent/workflow follows a strict structure required by DevUI's discovery system:

```
agent_name/
├── __init__.py      # Must export: agent = ChatAgent(...)
├── agent.py         # Agent implementation
└── .env.example     # Example environment variables
```

## Available Samples

### Agents

| Sample                                           | Description                                                                                       | Features                                                                   | Required Environment Variables                                                                     |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| [**weather_agent_azure/**](weather_agent_azure/) | Weather agent using Azure OpenAI with API key authentication                                      | Azure OpenAI integration, function calling, mock weather tools             | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, `AZURE_OPENAI_ENDPOINT`              |
| [**foundry_agent/**](foundry_agent/)             | Weather agent using Azure AI Agent (Foundry) with Azure CLI authentication (run `az login` first) | Azure AI Agent integration, Azure CLI authentication, mock weather tools   | `AZURE_AI_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT_NAME`                                       |

### Workflows

| Sample                                       | Description                                                       | Features                                                                                                                    | Required Environment Variables                                                        |
| -------------------------------------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| [**declarative/**](declarative/)             | Declarative YAML workflow with conditional branching              | YAML-based workflow definition, conditional logic, no Python code required                                                   | None - uses mock data                                                                 |
| [**workflow_agents/**](workflow_agents/)     | Content review workflow with agents as executors                  | Agents as workflow nodes, conditional routing based on structured outputs, quality-based paths (Writer -> Reviewer -> Editor/Publisher) | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`, `AZURE_OPENAI_ENDPOINT` |
| [**spam_workflow/**](spam_workflow/)         | 5-step email spam detection workflow with branching logic         | Sequential execution, conditional branching (spam vs. legitimate), multiple executors, mock spam detection                  | None - uses mock data                                                                 |
| [**fanout_workflow/**](fanout_workflow/)     | Advanced data processing workflow with parallel execution         | Fan-out/fan-in patterns, complex state management, multi-stage processing (validation -> transformation -> quality assurance) | None - uses mock data                                                                 |

### Standalone Examples

| Sample                                     | Description                                                               | Features                                                                                                                        |
| ------------------------------------------ | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| [**in_memory_mode.py**](in_memory_mode.py) | Demonstrates programmatic entity registration without directory structure | In-memory agent and workflow registration, multiple entities served from a single file, includes basic workflow, simplest way to get started |

## Environment Variables

Each sample that requires API keys includes a `.env.example` file. To use:

1. Copy `.env.example` to `.env` in the same directory
2. Fill in your actual API keys
3. DevUI automatically loads `.env` files from entity directories

Alternatively, set environment variables globally:

```bash
export OPENAI_API_KEY="your-key-here"
export OPENAI_CHAT_MODEL_ID="gpt-4o"
```

## Using DevUI with Your Own Agents

To make your agent discoverable by DevUI:

1. Create a folder for your agent
2. Add an `__init__.py` that exports `agent` or `workflow`
3. (Optional) Add a `.env` file for environment variables

Example:

```python
# my_agent/__init__.py
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

agent = ChatAgent(
    name="MyAgent",
    description="My custom agent",
    chat_client=OpenAIChatClient(),
    # ... your configuration
)
```

Then run:

```bash
devui /path/to/my/agents/folder
```

## API Usage

DevUI exposes OpenAI-compatible endpoints:

```bash
curl -X POST http://localhost:8080/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agent-framework",
    "input": "What is the weather in Seattle?",
    "extra_body": {"entity_id": "agent_directory_weather-agent_<uuid>"}
  }'
```

List available entities:

```bash
curl http://localhost:8080/v1/entities
```

## Learn More

- [DevUI Documentation](../../../packages/devui/README.md)
- [Agent Framework Documentation](https://docs.microsoft.com/agent-framework)
- [Sample Guidelines](../../SAMPLE_GUIDELINES.md)

## Troubleshooting

**Missing API keys**: Check your `.env` files or environment variables.

**Import errors**: Make sure you've installed the devui package:

```bash
pip install agent-framework-devui --pre
```

**Port conflicts**: DevUI uses ports 8080 (directory mode) and 8090 (in-memory mode) by default. Close other services or specify a different port:

```bash
devui --port 8888
```
