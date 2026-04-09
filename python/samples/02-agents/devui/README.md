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

### Option 1: In-Memory Mode (Programmatic Registration)

Run a single sample directly. This demonstrates how to register agents and workflows in code without using DevUI's directory discovery.

This sample uses Azure AI Foundry. Before running it:

1. Copy `.env.example` in this folder to `.env`, or export the same values in your shell
2. Set `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`
3. Run `az login`

Then start the sample:

```bash
cd python/samples/02-agents/devui
python in_memory_mode.py
```

This opens your browser at http://localhost:8090 with two Foundry-backed agents and a simple text transformation workflow.

### Option 2: Directory Discovery with Shared Root `.env`

Run the folder-level launcher to load `samples/02-agents/devui/.env` and then start DevUI with directory discovery for this folder:

```bash
cd python/samples/02-agents/devui
python main.py
```

This starts the server at http://localhost:8080 with all discoverable agents and workflows available. The root `.env` acts as shared fallback configuration for discovered samples.

### Option 3: Directory Discovery with the `devui` CLI

If you prefer the CLI directly, you can still launch DevUI from this folder:

```bash
cd python/samples/02-agents/devui
devui .
```

DevUI discovery checks for a sample-specific `.env` first and then falls back to `.env` in `samples/02-agents/devui/`.

## Sample Structure

DevUI discovers samples from Python packages that export either `agent` or `workflow`.

Typical agent layout:

```
agent_name/
├── __init__.py      # Must export: agent = ...
├── agent.py         # Agent implementation
└── .env.example     # Optional example environment variables
```

Typical workflow layout:

```
workflow_name/
├── __init__.py      # Must export: workflow = ...
├── workflow.py      # Workflow implementation
├── workflow.yaml    # Optional declarative definition
└── .env.example     # Optional example environment variables
```

## Available Samples

### Agents

| Sample | What it demonstrates | Required keys / auth |
| ------ | -------------------- | -------------------- |
| [**agent_weather/**](agent_weather/) | A richer Foundry-backed weather agent that shows chat middleware, function middleware, tool calling, and an approval-required tool alongside auto-approved tools. | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`, plus Azure CLI auth via `az login` |
| [**agent_foundry/**](agent_foundry/) | A minimal Foundry-backed weather agent with current weather and forecast tools. Use this when you want the smallest possible directory-discovered agent sample. | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`, plus Azure CLI auth via `az login` |

### Workflows

| Sample | What it demonstrates | Required keys / auth |
| ------ | -------------------- | -------------------- |
| [**workflow_declarative/**](workflow_declarative/) | A YAML-defined workflow loaded through `WorkflowFactory`, with nested age-based branching and no model client code. | None |
| [**workflow_with_agents/**](workflow_with_agents/) | A content review workflow that uses agents as executors and routes based on structured review output (`Writer -> Reviewer -> Editor/Publisher -> Summarizer`). | `AZURE_OPENAI_ENDPOINT`, plus `AZURE_OPENAI_CHAT_MODEL` or `AZURE_OPENAI_MODEL`; Azure CLI auth via `az login`; `AZURE_OPENAI_API_VERSION` is optional |
| [**workflow_spam/**](workflow_spam/) | A multi-step spam detection workflow with human-in-the-loop approval, branching for spam vs. legitimate messages, and a final reporting step. | None |
| [**workflow_fanout/**](workflow_fanout/) | A larger fan-out/fan-in data processing workflow with parallel validation, multiple transformations, QA, aggregation, and demo failure toggles. | None |

### Standalone Examples

| Sample | What it demonstrates | Required keys / auth |
| ------ | -------------------- | -------------------- |
| [**in_memory_mode.py**](in_memory_mode.py) | Registers multiple entities directly in Python: two Foundry-backed agents plus a simple workflow, all served from one file without directory discovery. | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`, plus Azure CLI auth via `az login` |

## Environment Variables

For samples that require external services:

1. Copy `.env.example` to `.env`
2. Fill in the required values
3. Run `az login` for samples that use Azure CLI authentication

Directory discovery checks `.env` files in this order:

1. The entity directory itself, for example `agent_weather/.env`
2. The root DevUI samples folder, `samples/02-agents/devui/.env`

That means the root `.env.example` can hold shared defaults for multiple samples, while a sample-specific `.env` can override those values when needed.

`in_memory_mode.py` and `main.py` both load `.env` from `samples/02-agents/devui/`, so the root `.env.example` in this folder is the right starting point for both commands.

Alternatively, set environment variables globally:

```bash
# Foundry-backed samples
export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com"
export FOUNDRY_MODEL="gpt-4o"

# Azure OpenAI workflow_with_agents sample
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com"
export AZURE_OPENAI_CHAT_MODEL="gpt-4o"
export AZURE_OPENAI_MODEL="gpt-4o"

az login
```

## Using DevUI with Your Own Agents

To make your agent discoverable by DevUI:

1. Create a folder for your agent
2. Add an `__init__.py` that exports `agent` or `workflow`
3. (Optional) Add a `.env` file for environment variables

Example:

```python
# my_agent/__init__.py
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

agent = Agent(
    name="MyAgent",
    description="My custom agent",
    client=OpenAIChatClient(),
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

**Missing credentials or settings**: Check your `.env` files, confirm the required variables for the sample you are running, and make sure `az login` has completed for Azure-authenticated samples.

**Import errors**: Make sure you've installed the devui package:

```bash
pip install agent-framework-devui --pre
```

**Port conflicts**: DevUI uses ports 8080 (directory mode) and 8090 (in-memory mode) by default. Close other services or specify a different port:

```bash
devui --port 8888
```
