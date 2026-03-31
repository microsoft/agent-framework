# Mem0 Context Provider Examples

[Mem0](https://mem0.ai/) is a self-improving memory layer for Large Language Models that enables applications to have long-term memory capabilities. The Agent Framework's Mem0 context provider integrates with Mem0's API to provide persistent memory across conversation sessions.

This folder contains examples demonstrating how to use the Mem0 context provider with the Agent Framework for persistent memory and context management across conversations.

## Examples

| File | Description |
|------|-------------|
| [`mem0_basic.py`](mem0_basic.py) | Basic example of using Mem0 context provider to store and retrieve user preferences across different conversation threads. |
| [`mem0_sessions.py`](mem0_sessions.py) | Example demonstrating different memory scoping strategies with Mem0. Covers user-scoped memory (memories shared across all sessions for the same user), agent-scoped memory (memories isolated per agent), and multiple agents with different memory configurations for personal vs. work contexts. |
| [`mem0_oss.py`](mem0_oss.py) | Example of using the Mem0 Open Source self-hosted version as the context provider. Demonstrates setup and configuration for local deployment. |

## Prerequisites

### Required Resources

1. [Mem0 API Key](https://app.mem0.ai/) - Sign up for a Mem0 account and get your API key - _or_ self-host [Mem0 Open Source](https://docs.mem0.ai/open-source/overview)
2. Azure AI project endpoint (used in these examples)
3. Azure CLI authentication (run `az login`)

## Configuration

### Environment Variables

Set the following environment variables:

**For Mem0 Platform:**
- `MEM0_API_KEY`: Your Mem0 API key (alternatively, pass it as `api_key` parameter to `Mem0Provider`). Not required if you are self-hosting [Mem0 Open Source](https://docs.mem0.ai/open-source/overview)

**For Mem0 Open Source:**
- `OPENAI_API_KEY`: Your OpenAI API key (used by Mem0 OSS for embedding generation and automatic memory extraction)

**For Azure AI:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI project endpoint
- `FOUNDRY_MODEL`: The name of your model deployment

## Key Concepts

### Memory Scoping

The Mem0 context provider supports scoping via identifiers:

- **User scope** (`user_id`): Associate memories with a specific user, shared across all sessions
- **Agent scope** (`agent_id`): Isolate memories per agent persona
- **Application scope** (`application_id`): Associate memories with an application context
