# Get Started with Agent Framework for Python

This folder contains a progressive set of samples that introduce the core
concepts of **Agent Framework** one step at a time.

## Prerequisites

```bash
pip install agent-framework-foundry azure-identity
az login
```

Each sample hardcodes example values for `project_endpoint` and `model`. Replace them with your Microsoft Foundry
project endpoint and model deployment name before running the sample.

Alternatively, set `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL`, then remove the `project_endpoint` and `model`
arguments from the `FoundryChatClient` constructor. To read those values from a `.env` file, call `load_dotenv()`
before creating the client; Agent Framework doesn't load `.env` files automatically.

## Samples

| # | File | What you'll learn |
|---|------|-------------------|
| 1 | [01_hello_agent.py](01_hello_agent.py) | Create your first agent and run one request. |
| 2 | [02_add_tools.py](02_add_tools.py) | Define a function tool with `@tool` and attach it to an agent. |
| 3 | [03_multi_turn.py](03_multi_turn.py) | Reuse an agent session to keep conversation history across turns. |
| 4 | [04_memory.py](04_memory.py) | Store and inject session state with a custom `ContextProvider`. |
| 5 | [05_functional_workflow_with_agents.py](05_functional_workflow_with_agents.py) | Call agents inside a functional workflow. |
| 6 | [06_functional_workflow_basics.py](06_functional_workflow_basics.py) | Write a workflow as a plain async function. |
| 7 | [07_first_graph_workflow.py](07_first_graph_workflow.py) | Connect function executors with a graph edge. |

To host agents and workflows with Durable Task or Azure Functions, continue with the [Durable Agent Framework extension samples](https://github.com/microsoft/agent-framework-durable-extension/tree/main/python/samples).

## Security in Production

Introductory tutorials in this directory demonstrate core agent mechanics with minimal wiring. When building agents for production that handle untrusted external content (emails, user attachments, web browsing, third-party APIs) or execute privileged actions, incorporate security controls against indirect prompt injection and data exfiltration.

For the official security guidance, see [Agent Safety](https://learn.microsoft.com/en-us/agent-framework/concepts/agents/safety) on Microsoft Learn. Then see [`samples/02-agents/security/`](../02-agents/security/) for production-ready security patterns:

1. [`email_security_example.py`](../02-agents/security/email_security_example.py): Demonstrates `SecureAgentConfig`, isolated execution using `quarantined_llm`, and approval gating before invoking sensitive tools.
2. [`repo_confidentiality_example.py`](../02-agents/security/repo_confidentiality_example.py): Demonstrates tracking data confidentiality to prevent sensitive data leaks.
3. [`github_mcp_example.py`](../02-agents/security/github_mcp_example.py): Demonstrates `SecureMCPToolProxy` wrapping remote MCP endpoints with local policy enforcement.
4. [FIDES Developer Guide](../02-agents/security/FIDES_DEVELOPER_GUIDE.md): Architecture reference and security middleware documentation.

Run any sample with:

```bash
python 01_hello_agent.py
```

These samples use Azure Foundry models with the Responses API. To switch providers, just replace the client, see [all providers](../02-agents/providers/README.md)
