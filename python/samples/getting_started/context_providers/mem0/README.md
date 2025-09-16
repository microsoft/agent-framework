# Mem0 Context Provider Examples

[Mem0](https://mem0.ai/) is a self-improving memory layer for Large Language Models that enables applications to have long-term memory capabilities. The Agent Framework's Mem0 context provider integrates with Mem0's API to provide persistent memory across conversation sessions.

This folder contains examples demonstrating how to use the Mem0 context provider with the Agent Framework for persistent memory and context management across conversations.

## Examples

| File | Description |
|------|-------------|
| [`mem0_basic.py`](mem0_basic.py) | Basic example of using Mem0 context provider to store and retrieve user preferences across different conversation threads. |
| [`mem0_threads.py`](mem0_threads.py) | Advanced example demonstrating different thread scoping strategies with Mem0. Covers global thread scope (memories shared across all operations), per-operation thread scope (memories isolated per thread), and multiple agents with different memory configurations for personal vs. work contexts. |

## Prerequisites

### Required Resources

1. [Mem0 API Key](https://app.mem0.ai/) - Sign up for a Mem0 account and get your API key
2. Azure AI Foundry project endpoint (used in these examples)
3. Azure CLI authentication (run `az login`)

## Configuration

### Environment Variables

Set the following environment variables:

**For Mem0:**
- `MEM0_API_KEY`: Your Mem0 API key (alternatively, pass it as `api_key` parameter to `Mem0Provider`)

**For Azure AI Foundry:**
- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL_DEPLOYMENT_NAME`: The name of your model deployment

## Key Concepts

### Memory Scoping

The Mem0 context provider supports different scoping strategies:

- **Global Scope** (`scope_to_per_operation_thread_id=False`): Memories are shared across all conversation threads
- **Thread Scope** (`scope_to_per_operation_thread_id=True`): Memories are isolated per conversation thread

### Memory Association

Mem0 records can be associated with different identifiers:

- `user_id`: Associate memories with a specific user
- `agent_id`: Associate memories with a specific agent
- `thread_id`: Associate memories with a specific conversation thread
- `application_id`: Associate memories with an application context
