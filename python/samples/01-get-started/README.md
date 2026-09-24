# Get Started with Agent Framework for Python

This folder contains a progressive set of samples that introduce the core
concepts of **Agent Framework** one step at a time.

## Prerequisites

```bash
pip install agent-framework-foundry
```

Sample 08 additionally requires `agent-framework-azurefunctions --pre`.

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
| 5 | [05_functional_workflow_with_agents.py](05_functional_workflow_with_agents.py) | Call agents inside a functional workflow. |
| 6 | [06_functional_workflow_basics.py](06_functional_workflow_basics.py) | Write a workflow as a plain async function. |
| 7 | [07_first_graph_workflow.py](07_first_graph_workflow.py) | Chain executors into a graph workflow with edges. |

To host agents and workflows with Durable Task or Azure Functions, continue with the [Durable Agent Framework extension samples](https://github.com/microsoft/agent-framework-durable-extension/tree/main/python/samples).

## Security in Production

Introductory tutorials in this directory demonstrate core agent mechanics with minimal wiring. When building agents for production that handle untrusted external content (emails, user attachments, web browsing, third-party APIs) or execute privileged actions, incorporate security controls against indirect prompt injection and data exfiltration.

See [`samples/02-agents/security/`](../02-agents/security/) for production-ready security patterns:

1. [`email_security_example.py`](../02-agents/security/email_security_example.py): Demonstrates `SecureAgentConfig`, isolated execution using `quarantined_llm`, and approval gating before invoking sensitive tools.
2. [`repo_confidentiality_example.py`](../02-agents/security/repo_confidentiality_example.py): Demonstrates tracking data confidentiality to prevent sensitive data leaks.
3. [`github_mcp_example.py`](../02-agents/security/github_mcp_example.py): Demonstrates `SecureMCPToolProxy` wrapping remote MCP endpoints with local policy enforcement.
4. [FIDES Developer Guide](../02-agents/security/FIDES_DEVELOPER_GUIDE.md): Architecture reference and security middleware documentation.

Run any sample with:

```bash
python 01_hello_agent.py
```

These samples use Azure Foundry models with the Responses API. To switch providers, just replace the client, see [all providers](../02-agents/providers/README.md)
