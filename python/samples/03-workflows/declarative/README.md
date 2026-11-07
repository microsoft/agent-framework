# Declarative Workflows

Declarative workflows allow you to define multi-agent orchestration patterns in YAML, including:
- Variable manipulation and state management
- Control flow (loops, conditionals, branching)
- Agent invocations
- Human-in-the-loop patterns

See the [main workflows README](../README.md#declarative) for the list of available samples.

## Prerequisites

```bash
pip install agent-framework-declarative
```

## Running Samples

Each sample directory contains:
- `workflow.yaml` - The declarative workflow definition
- `main.py` - Python code to load and execute the workflow
- `README.md` - Sample-specific documentation

To run a sample:

```bash
cd <sample_directory>
python main.py
```

## Workflow Structure

A basic workflow YAML file looks like:

```yaml
name: my-workflow
description: A simple workflow example

actions:
  - kind: SetValue
    path: turn.greeting
    value: Hello, World!

  - kind: SendActivity
    activity:
      text: =turn.greeting
```

## Action Types

### Variable Actions
- `SetValue` - Set a variable in state
- `SetVariable` - Set a variable (.NET style naming)
- `ResetVariable` - Clear a variable

### Control Flow
- `If` - Conditional branching
- `ConditionGroup` - Multi-way branching
- `Foreach` - Iterate over collections
- `GotoAction` - Jump to labeled action

### Output
- `SendActivity` - Send text/attachments to user

### Agent Invocation
- `InvokeAzureAgent` - Call an Azure AI agent

### Tool Invocation
- `InvokeFunctionTool` - Call a registered Python function
- `InvokeMcpTool` - Call an MCP tool through a host-supplied handler

The `invoke_mcp_tool` and `invoke_foundry_toolbox_mcp` samples use
`DefaultMCPToolHandler`. Create this handler as a normal object; it has no
shutdown method or async context manager. Each invocation connects and closes
a fresh MCP protocol session, including calls after approval waits or checkpoint
resumes. Do not rely on implicit server-side session state between calls.

The toolbox sample supplies a caller-owned HTTP client through `client_provider`
to reuse its authenticated HTTP connection pool without sharing MCP sessions.
Keep that client's context open until every workflow call has finished; cancel
and await outstanding calls before closing it.

### Human-in-Loop
- `Question` - Request user input
- `RequestExternalInput` - Request external data/approval
