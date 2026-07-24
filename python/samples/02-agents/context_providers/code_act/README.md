# CodeAct context providers

Demonstrates the provider-owned CodeAct flow with three backends:

| File | Backend | Notes |
|------|---------|-------|
| [`code_act.py`](code_act.py) | [Hyperlight](https://github.com/hyperlight-dev/hyperlight) WASM sandbox via `HyperlightCodeActProvider` | Hardened sandbox with WASM isolation; sandbox tools called via `call_tool(...)`. |
| [`monty_code_act.py`](monty_code_act.py) | [Monty](https://github.com/pydantic/monty) Rust-based Python interpreter via `MontyCodeActProvider` (beta) | Cross-platform pure interpreter; sandbox tools can be called as typed async functions (`await compute(...)`) or via `call_tool(...)`. |
| [`tenki_code_act.py`](tenki_code_act.py) | [Tenki](https://tenki.cloud) managed Linux micro-VM via `TenkiCodeActProvider` (alpha) | Full Linux userland with `subprocess`, `apt`, and a persistent filesystem across `execute_code` calls; in-sandbox tool callbacks not supported. |

The Hyperlight and Monty providers register sandbox-only tools (`compute`,
`fetch_data`) that the model invokes from inside the sandbox. The Tenki provider
does not register sandbox-scoped host tools — the Tenki SDK has no callback
bridge — but exposes a much wider environment (real subprocesses, network,
package installs).

## Installation

```bash
pip install agent-framework-hyperlight agent-framework-foundry --pre  # Hyperlight sample
pip install agent-framework-monty agent-framework-foundry --pre       # Monty sample
pip install agent-framework-tenki agent-framework-foundry --pre       # Tenki sample
```

> The Hyperlight Wasm backend is currently published only for `linux/x86_64` and
> `win32/AMD64` with Python `<3.14`. On other platforms `execute_code` will fail
> at runtime when it tries to create the sandbox.
>
> Monty is cross-platform and has no hypervisor/WASM backend dependency, but it
> interprets a Python subset (e.g. `os`/network/subprocess access is blocked).
> The beta `agent-framework-monty` package is included in `agent-framework[all]`.
>
> Tenki runs code in a managed Linux micro-VM on the Tenki service, so it needs
> `TENKI_API_KEY` (and `TENKI_PROJECT_ID` when the key spans multiple projects).
> `agent-framework-tenki` is an alpha package and is not yet part of
> `agent-framework[all]`; install it explicitly with `--pre`.

## Prerequisites

- A Microsoft Foundry project endpoint (`FOUNDRY_PROJECT_ENDPOINT`)
- A deployed model (`FOUNDRY_MODEL`)
- Azure CLI authenticated (`az login`)

## Run

```bash
python code_act.py        # Hyperlight
python monty_code_act.py  # Monty
python tenki_code_act.py  # Tenki (also needs TENKI_API_KEY)
```

See the source files for the full annotated examples.
