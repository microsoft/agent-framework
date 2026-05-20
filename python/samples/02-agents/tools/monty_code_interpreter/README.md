# Monty local code interpreter

Demonstrates the standalone [Monty](https://github.com/pydantic/monty)
`MontyExecuteCodeTool` — a sandboxed local code interpreter that the agent can
invoke directly. Two patterns are shown:

| File | Pattern |
|------|---------|
| [`monty_code_interpreter.py`](monty_code_interpreter.py) | **Standalone tool** — `MontyExecuteCodeTool` is added to the agent tool list and self-describes its sandbox tools, so no extra agent instructions are needed. Best for quick prototyping. |
| [`monty_code_interpreter_manual_wiring.py`](monty_code_interpreter_manual_wiring.py) | **Manual static wiring** — sandbox tools and CodeAct instructions are built once and passed to the `Agent` constructor alongside a direct-only tool (`send_email`). Best when the tool set is fixed for the agent's lifetime. |

For the recommended provider-driven pattern (with dynamic tool / capability
management), see
[`../../context_providers/code_act/`](../../context_providers/code_act/).

## Installation

```bash
pip install agent-framework agent-framework-monty --pre
```

> `agent-framework-monty` is an alpha package and is not yet part of
> `agent-framework[all]`. The `--pre` flag is required.
>
> Monty is cross-platform and has no hypervisor/WASM backend dependency.
> Inside the sandbox, OS / filesystem / network calls are blocked
> (`PermissionError`); registered host tools retain full Python access.

## Prerequisites

- An Azure AI Foundry project endpoint (`FOUNDRY_PROJECT_ENDPOINT`)
- A deployed model (`FOUNDRY_MODEL`)
- Azure CLI authenticated (`az login`)

## Run

```bash
python monty_code_interpreter.py
python monty_code_interpreter_manual_wiring.py
```
