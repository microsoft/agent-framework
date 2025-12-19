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
- `AppendValue` - Append to a list
- `ResetVariable` - Clear a variable

### Control Flow
- `If` - Conditional branching
- `Switch` - Multi-way branching
- `Foreach` - Iterate over collections
- `RepeatUntil` - Loop until condition
- `GotoAction` - Jump to labeled action

### Output
- `SendActivity` - Send text/attachments to user
- `EmitEvent` - Emit custom events

### Agent Invocation
- `InvokeAzureAgent` - Call an Azure AI agent
- `InvokePromptAgent` - Call a local prompt agent

### Human-in-Loop
- `Question` - Request user input
- `WaitForInput` - Pause for external input
