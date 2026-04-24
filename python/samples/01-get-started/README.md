# Get Started with Agent Framework for Python

This folder contains a progressive set of samples that introduce the core
concepts of **Agent Framework** one step at a time.

## Prerequisites

```bash
pip install agent-framework
```

Set the required environment variables:

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://your-project-endpoint"
export FOUNDRY_MODEL="gpt-4o"   # optional, defaults to gpt-4o
```

## Samples

| # | File | What you'll learn |
|---|------|-------------------|
| 1 | [01_hello_agent.py](01_hello_agent.py) | Create your first agent and run it (streaming and non-streaming). |
| 2 | [02_add_tools.py](02_add_tools.py) | Define a function tool with `@tool` and attach it to an agent. |
| 3 | [03_multi_turn.py](03_multi_turn.py) | Keep conversation history across turns with `AgentSession`. |
| 4 | [04_memory.py](04_memory.py) | Add dynamic context with a custom `ContextProvider`. |
| 5 | [05_first_workflow.py](05_first_workflow.py) | Chain executors into a workflow with edges. |
| 6 | [06_host_your_agent.py](06_host_your_agent.py) | Host a single agent with Azure Functions. |

Run any sample with:

```bash
python 01_hello_agent.py
```

These samples use Azure Foundry models with the Responses API. To switch providers, just replace the client, see [all providers](../02-agents/providers/README.md)
