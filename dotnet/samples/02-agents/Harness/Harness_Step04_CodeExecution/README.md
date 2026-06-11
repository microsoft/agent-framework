# Harness Step 04 — Code Execution (Hyperlight + Skills)

This sample demonstrates a HarnessAgent with **all features enabled**, plus:

- **Hyperlight CodeAct** — sandboxed Python code execution via `execute_code` (requires KVM)
- **Skills** — file-based skill discovery (a `regex-tester` skill is included)

The agent can plan tasks, manage modes, store memories, read/write files, search the web, approve sensitive operations, discover and use skills, and execute arbitrary Python code — all pre-configured by the HarnessAgent.

## Prerequisites

- .NET 10 SDK
- An Azure AI Foundry project endpoint
- KVM-capable host (the Hyperlight sandbox runs code in micro-VMs)

## Environment Variables

| Variable | Description |
|----------|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | Your Azure AI Foundry project endpoint |
| `FOUNDRY_MODEL` | Model deployment name (default: `gpt-5.4`) |

## Running

```bash
dotnet run
```

## What to Try

- **Regex testing**: "Help me write a regex that matches valid email addresses, then test it against some examples."
- **Code execution**: "Calculate the first 20 prime numbers using the Sieve of Eratosthenes."
- **Skill + code combo**: "I need a regex for ISO 8601 dates — test it thoroughly with edge cases."

## Included Skill

The `skills/regex-tester/` skill instructs the agent to validate regex patterns by executing Python test code in the Hyperlight sandbox. It includes a regex cheatsheet as reference material.

## Features Enabled

| Feature | Description |
|---------|-------------|
| TodoProvider | Task planning and tracking (`/todos` command) |
| AgentModeProvider | Mode switching (`/mode` command) |
| FileMemoryProvider | Persistent memory stored as files |
| FileAccessProvider | Read/write files in a working directory |
| ToolApproval | Don't-ask-again approval for sensitive tools |
| WebSearch | Built-in hosted web search |
| AgentSkillsProvider | Discovers and uses skills from the `skills/` folder |
| HyperlightCodeActProvider | Sandboxed Python execution via `execute_code` |
| OpenTelemetry | Trace logging to a text file |
