# Hyperlight local code interpreter

Demonstrates the standalone [Hyperlight](https://github.com/hyperlight-dev/hyperlight)
`HyperlightExecuteCodeTool` — a sandboxed local code interpreter that the agent
can invoke directly. Two patterns are shown:

| File | Pattern |
|------|---------|
| [`local_code_interpreter.py`](local_code_interpreter.py) | **Standalone tool** — `HyperlightExecuteCodeTool` is added to the agent tool list and self-describes its sandbox tools, so no extra agent instructions are needed. Best for quick prototyping. |
| [`local_code_interpreter_manual_wiring.py`](local_code_interpreter_manual_wiring.py) | **Manual static wiring** — sandbox tools and CodeAct instructions are built once and passed to the `Agent` constructor alongside a direct-only tool (`send_email`). Best when the tool set is fixed for the agent's lifetime. |

For the recommended provider-driven pattern (with dynamic tool / capability
management), see
[`../../context_providers/code_act/`](../../context_providers/code_act/).

## Installation

```bash
pip install agent-framework agent-framework-hyperlight --pre
```

> The Hyperlight Wasm backend is currently published only for `linux/x86_64` and
> `win32/AMD64` with Python `<3.14`. On other platforms `execute_code` will fail
> at runtime when it tries to create the sandbox.

## Prerequisites

- An Azure AI Foundry project endpoint (`FOUNDRY_PROJECT_ENDPOINT`)
- A deployed model (`FOUNDRY_MODEL`)
- Azure CLI authenticated (`az login`)

## Run

```bash
python local_code_interpreter.py
python local_code_interpreter_manual_wiring.py
```
