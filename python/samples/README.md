# Python Samples

This directory contains samples demonstrating the capabilities of Microsoft Agent Framework for Python.

## Structure

| Folder | Description |
|--------|-------------|
| [`01-get-started/`](./01-get-started/) | Progressive tutorial: hello agent → hosting |
| [`02-agents/`](./02-agents/) | Deep-dive by concept: tools, middleware, providers, orchestrations |
| [`03-workflows/`](./03-workflows/) | Workflow patterns: sequential, concurrent, state, declarative |
| [`04-hosting/`](./04-hosting/) | Deployment: Azure Functions, Durable Tasks, A2A |
| [`05-end-to-end/`](./05-end-to-end/) | Full applications, evaluation, demos |

## Getting Started

Start with `01-get-started/` and work through the numbered files:

1. **[01_hello_agent.py](./01-get-started/01_hello_agent.py)** — Create and run your first agent
2. **[02_add_tools.py](./01-get-started/02_add_tools.py)** — Add function tools with `@tool`
3. **[03_multi_turn.py](./01-get-started/03_multi_turn.py)** — Multi-turn conversations with `AgentThread`
4. **[04_memory.py](./01-get-started/04_memory.py)** — Agent memory with `ContextProvider`
5. **[05_first_workflow.py](./01-get-started/05_first_workflow.py)** — Build a workflow with executors and edges
6. **[06_host_your_agent.py](./01-get-started/06_host_your_agent.py)** — Host your agent via A2A

## Prerequisites

```bash
pip install agent-framework --pre
```

Set the following environment variables for the getting-started samples:

```bash
export AZURE_AI_PROJECT_ENDPOINT="your-foundry-project-endpoint"
export AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME="gpt-4o"
```

For Azure authentication, run `az login` before running samples.

## Note on XML tags

Some sample files include XML-style snippet tags (for example `<snippet_name>` and `</snippet_name>`). These are used by our documentation tooling and can be ignored or removed when you use the samples outside this repository.

## Additional Resources

- [Agent Framework Documentation](https://learn.microsoft.com/agent-framework/)
- [AGENTS.md](./AGENTS.md) — Structure documentation for maintainers
- [SAMPLE_GUIDELINES.md](./SAMPLE_GUIDELINES.md) — Coding conventions for samples
