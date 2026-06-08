# CodeAct context providers

Demonstrates the provider-owned CodeAct flow with two backends:

| File | Backend | Notes |
|------|---------|-------|
| [`code_act.py`](code_act.py) | [Hyperlight](https://github.com/hyperlight-dev/hyperlight) WASM sandbox via `HyperlightCodeActProvider` | Hardened sandbox with WASM isolation; sandbox tools called via `call_tool(...)`. |
| [`monty_code_act.py`](monty_code_act.py) | [Monty](https://github.com/pydantic/monty) Rust-based Python interpreter via `MontyCodeActProvider` (alpha) | Cross-platform pure interpreter; sandbox tools can be called as typed async functions (`await compute(...)`) or via `call_tool(...)`. |

Both providers inject an `execute_code` tool into the agent and keep the
registered sandbox tools (`compute`, `fetch_data`) hidden from the model — the
model invokes them from inside the sandbox.

## Installation

```bash
pip install agent-framework agent-framework-hyperlight --pre   # Hyperlight sample
pip install agent-framework agent-framework-monty --pre        # Monty sample
```

> The Hyperlight Wasm backend is currently published only for `linux/x86_64` and
> `win32/AMD64` with Python `<3.14`. On other platforms `execute_code` will fail
> at runtime when it tries to create the sandbox.
>
> Monty is cross-platform and has no hypervisor/WASM backend dependency, but it
> interprets a Python subset (e.g. `os`/network/subprocess access is blocked).
> `agent-framework-monty` is an alpha package and is not yet part of
> `agent-framework[all]`; install it explicitly with `--pre`.

## Prerequisites

- An Azure AI Foundry project endpoint (`FOUNDRY_PROJECT_ENDPOINT`)
- A deployed model (`FOUNDRY_MODEL`)
- Azure CLI authenticated (`az login`)

## Run

```bash
python code_act.py        # Hyperlight
python monty_code_act.py  # Monty
```

See the source files for the full annotated examples.
