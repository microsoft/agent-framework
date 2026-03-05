# Get Started with Agent Framework for Python

This folder contains a progressive set of samples that introduce the core
concepts of **Agent Framework** one step at a time.

## Prerequisites

```bash
pip install agent-framework --pre
```

Set the required environment variables:

```bash
export AZURE_AI_PROJECT_ENDPOINT="https://your-project-endpoint"
export AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME="gpt-4o"   # optional, defaults to gpt-4o
```

## Samples

| # | File | What you'll learn |
|---|------|-------------------|
| 1 | [01_hello_agent.py](01_hello_agent.py) | Create your first agent and run it (streaming and non-streaming). |
| 2 | [02_add_tools.py](02_add_tools.py) | Define a function tool with `@tool` and attach it to an agent. |
| 3 | [03_multi_turn.py](03_multi_turn.py) | Keep conversation history across turns with `AgentThread`. |
| 4 | [04_memory.py](04_memory.py) | Add dynamic context with a custom `ContextProvider`. |
| 5 | [05_functional_workflow_with_agents.py](05_functional_workflow_with_agents.py) | Call agents inside a functional workflow. |
| 6 | [06_first_functional_workflow.py](06_first_functional_workflow.py) | Write a workflow as a plain async function. |
| 7 | [07_first_graph_workflow.py](07_first_graph_workflow.py) | Chain executors into a graph workflow with edges. |
| 8 | [08_host_your_agent.py](08_host_your_agent.py) | Host a single agent with Azure Functions. |

Run any sample with:

```bash
python 01_hello_agent.py
```

These samples use Azure Foundry models with the Responses API. To switch providers, just replace the client, see [all providers](../02-agents/providers/README.md)
