# agent-sandbox CodeAct context provider

Demonstrates `AgentSandboxCodeActProvider`: every `execute_code` call runs
LLM-emitted Python inside a Kubernetes Pod claimed from a `SandboxWarmPool` and
managed by the [`kubernetes-sigs/agent-sandbox`](https://github.com/kubernetes-sigs/agent-sandbox)
controller. Unlike an in-process snapshot-and-restore sandbox, the Pod's working
directory and any `pip install`-ed packages persist across calls.

This sample uses `OllamaChatClient`, so it runs **without any API key**.

## Installation

```bash
pip install agent-framework agent-framework-agentsandbox agent-framework-ollama --pre
```

## Prerequisites

- A Kubernetes cluster with the agent-sandbox controller installed, plus a
  `SandboxTemplate` and a `SandboxWarmPool` (default name `python-sandbox-pool`).
- The `sandbox-router` reachable on `localhost:8080` (the async client uses a
  direct connection, so run `kubectl -n default port-forward svc/sandbox-router-svc 8080:8080`).
- Ollama running locally with a tool-capable model, e.g. `ollama pull qwen2.5`.

See the package's [`TESTING.md`](../../../../packages/agentsandbox/TESTING.md)
for a complete local walkthrough.

## Configuration

| Environment variable | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL` | (Ollama default) | Model to use; must support tool calling |
| `AGENT_SANDBOX_WARMPOOL` | `python-sandbox-pool` | Warm pool to claim from |
| `AGENT_SANDBOX_NAMESPACE` | `default` | Namespace holding the warm pool |
| `AGENT_SANDBOX_ROUTER_URL` | `http://localhost:8080` | Router endpoint |

## Run

```bash
python agentsandbox_codeact.py
```

See [`agentsandbox_codeact.py`](agentsandbox_codeact.py) for the annotated example.

## Related

- [`code_act/`](../code_act/) — the same `ContextProvider` shape backed by an
  in-process Hyperlight WASM sandbox (stateless per call).
