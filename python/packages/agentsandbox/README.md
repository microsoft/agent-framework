# agent-framework-agentsandbox

agent-sandbox-backed CodeAct integration for Microsoft Agent Framework. Runs LLM-emitted Python inside an isolated Kubernetes Pod managed by the [`kubernetes-sigs/agent-sandbox`](https://github.com/kubernetes-sigs/agent-sandbox) controller — with persistent filesystem state across calls, `pip install` survival, optional gVisor / Kata isolation, and `SandboxWarmPool` for sub-second cold starts.

> **Status: experimental / alpha.** Requires `k8s-agent-sandbox>=0.5.0`, the first release with the native async client (`AsyncSandboxClient` / `AsyncSandbox`) and the warm-pool claim API (`create_sandbox(warmpool=...)`).

## When to use this

`agent-framework-hyperlight` is the in-process WASM CodeAct backend — microsecond startup, snapshot-and-restore per call, ideal for short stateless computations.

`agent-framework-agentsandbox` is the **remote, persistent, container-grade** alternative. Use it when the agent needs to `pip install` a package and use it next call, read/produce real files, use libraries that don't run in WASM, run for minutes against a working dataset, be hardened with gVisor / Kata, or run on infrastructure the team already operates.

## Quick start

### Context provider (recommended)

```python
from agent_framework import Agent
from agent_framework.ollama import OllamaChatClient
from agent_framework.agentsandbox import AgentSandboxCodeActProvider
from k8s_agent_sandbox.models import SandboxDirectConnectionConfig

async with AgentSandboxCodeActProvider(
    warmpool="python-sandbox-pool",
    namespace="default",
    # The async client reaches the Pod through the sandbox-router. Point it at a
    # local `kubectl port-forward svc/sandbox-router-svc 8080:8080`, an
    # in-cluster service, or a Gateway. Local kubectl-tunnel mode is not
    # supported by the async client.
    connection_config=SandboxDirectConnectionConfig(api_url="http://localhost:8080"),
    shutdown_after_seconds=30 * 60,
) as codeact:
    agent = Agent(
        client=OllamaChatClient(),
        instructions="Use execute_code for computation; print the answer.",
        context_providers=[codeact],
    )
    result = await agent.run("What is the 30th Fibonacci number?")
    print(result.text)
```

The provider lazily claims one Sandbox Pod from the warm pool on the first `execute_code` call and reuses it across every run on this agent until you exit the `async with` block.

### Standalone tool

```python
from agent_framework import Agent
from agent_framework.agentsandbox import AgentSandboxExecuteCodeTool

execute_code = AgentSandboxExecuteCodeTool(
    warmpool="python-sandbox-pool",
    namespace="default",
    connection_config=...,
)
try:
    agent = Agent(client=..., tools=[my_direct_tool, execute_code])
    # ...
finally:
    await execute_code.close()
```

## Configuration

Most knobs live where they belong in Kubernetes, not on the Python constructor:

- **CPU / memory / image / volumes / runtime class / security context** → `SandboxTemplate.spec.podTemplate`.
- **Pre-warming / pooling** → `SandboxWarmPool` (references the template); the provider claims from it by name.
- **Network egress allow-listing** → Kubernetes `NetworkPolicy`.
- **File mounts** → template `Volumes`, or `sandbox.files.write` / `read` at runtime.

Python-side knobs:

| Argument | Default | Purpose |
|---|---|---|
| `warmpool` (required) | — | `SandboxWarmPool` to claim from |
| `namespace` | `"default"` | Kubernetes namespace |
| `connection_config` (required) | — | `SandboxDirectConnectionConfig` / `SandboxGatewayConnectionConfig` / `SandboxInClusterConnectionConfig` |
| `shutdown_after_seconds` | `None` | Safety net: controller auto-deletes the claim after this TTL |
| `labels` | `None` | Extra Kubernetes labels on the claim |
| `approval_mode` | `"never_require"` | Framework's tool-approval gate |
| `python_command` | `"python3 -u"` | Interpreter invocation |
| `exec_timeout` | `120` | Per-call subprocess timeout (seconds) |

## How it talks to the sandbox

It uses the agent-sandbox **async** SDK (`AsyncSandboxClient` / `AsyncSandbox`) directly — no thread offloading inside Agent Framework's async run loop. Each `execute_code` call:

1. `await sandbox.files.write("_agent_sandbox_exec_<uuid>.py", code)` — ships the source as a file into the Pod's `/app` working directory under a per-call unique name, so concurrent `execute_code` calls in one turn never clobber each other (sidesteps shell quoting; the model gets real tracebacks with file/line info).
2. `await sandbox.commands.run("python3 -u _agent_sandbox_exec_<uuid>.py")` via the Pod's `/execute` endpoint (commands run from `/app`).
3. Maps `stdout` / `stderr` / `exit_code` into `Content` objects: stdout as text, stderr appended on success, or `Content.from_error(...)` on non-zero exit.

### Runtime notes

- **`pip install` location.** The reference `python-runtime-sandbox` image runs as a non-root user whose `HOME` is read-only, so a plain `pip install <pkg>` fails with a permission error (it cannot write `/.local` / `/.cache`). The working directory `/app` is writable — install under it and extend `sys.path`, e.g. `pip install --target=/app/.pkgs <pkg>` then `sys.path.insert(0, "/app/.pkgs")`. Packages installed this way persist on the Pod across `execute_code` calls. A runtime image with a writable `HOME` makes a plain `pip install` work too; this is an image choice, not a limitation of the integration.
- **Router authentication.** This package reaches the Pod through the agent-sandbox `sandbox-router`. Recent router builds require auth (`ROUTER_AUTH_TOKEN`) and refuse to start otherwise, unless `ALLOW_UNAUTHENTICATED_ROUTER=true` is set. The `k8s-agent-sandbox` SDK does not send a token yet, so the router must run in unauthenticated mode for this integration to reach it.

## Comparison with `agent-framework-hyperlight`

| | `hyperlight` | `agentsandbox` |
|---|---|---|
| Runtime | In-process WASM micro-VM | Kubernetes Pod |
| Startup | Microseconds | Seconds (sub-second with `SandboxWarmPool`) |
| State across calls | Snapshot-and-restore — clean each call | Persistent — filesystem + packages stay |
| Isolation | VM-level, no Linux kernel | Container + optional gVisor / Kata |
| Pool / pre-warm | In-process registry | `SandboxWarmPool` controller |

## Testing

See [`TESTING.md`](TESTING.md) for a full local end-to-end walkthrough (kind cluster + Ollama, no API keys) and [`samples/02-agents/context_providers/agentsandbox_codeact/`](../../samples/02-agents/context_providers/agentsandbox_codeact/) for a runnable demo.

