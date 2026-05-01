# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent that
runs Python in a [Hyperlight](https://github.com/hyperlight-dev/hyperlight)
WebAssembly sandbox via the **CodeAct** pattern, hosted using the **Responses
protocol**. The model is only given a single `execute_code` tool. Local Python
tools (`compute`, `fetch_data`) are registered on `HyperlightCodeActProvider`
and are reachable from inside the sandbox via `call_tool(...)`, never as
direct LLM tools.

## How It Works

### Model integration

The agent uses `FoundryChatClient` to talk to a Foundry-hosted model deployment.
A `HyperlightCodeActProvider` is attached as a context provider, which on every
run injects the `execute_code` tool plus the CodeAct instructions that teach the
model how to author Python that calls `call_tool(...)` for sandbox-only tools.

See [`main.py`](main.py) for the full implementation.

### Agent hosting

The agent is hosted with `ResponsesHostServer` from
`agent-framework-foundry-hosting`, which exposes a REST endpoint compatible with
the OpenAI Responses protocol.

> The Hyperlight Wasm backend is currently published only for `linux/x86_64` and
> `win32/AMD64` with Python `<3.14`. The hosted container runs `python:3.12-slim`
> on linux/x86_64, which is supported.

### Hypervisor requirement

Hyperlight executes guest WebAssembly inside a micro-VM and **requires a
hypervisor on the host**:

- **Linux:** `/dev/kvm` must be present *and* the container must have access to
  it (`docker run --device=/dev/kvm ...`).
- **Windows:** the Microsoft Hypervisor Platform (MSHV) must be enabled.

Without a hypervisor, sandbox creation fails with:

```
Failed to create sandbox: failed to build ProtoWasmSandbox: No Hypervisor was found for Sandbox
```

This affects hosted environments that don't expose `/dev/kvm` to the workload
container (most managed PaaS, including the default Foundry hosted-agent
runtime). To run this sample as a hosted agent you need a hosting target with
nested virtualization and `/dev/kvm` device passthrough — for example an Azure
VM, AKS nodes with KVM enabled, or Azure Container Instances configured for
nested virt.

## Running the Agent Host

Follow the instructions in the
[Running the Agent Host Locally](../../README.md#running-the-agent-host-locally)
section of the README in the parent directory.

## Interacting with the agent

Send a POST request to the server with a JSON body containing an `"input"`
field. The model should respond by calling `execute_code` with Python that uses
`call_tool(...)` to reach the sandbox-only tools:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Fetch all users, find the admins, multiply 7 by 6, and print the users, admins and multiplication result. Use execute_code with call_tool(...)."}'
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the
[Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry)
section of the parent README.

### Deploying with in-tree (local) packages

This sample's Dockerfile installs `agent-framework-core`, `-openai`, `-foundry`,
`-foundry-hosting`, and `-hyperlight` from local source under `python/packages/`
instead of from PyPI, so you can validate unreleased fixes end-to-end. The
Dockerfile expects the repository's `python/` directory as the build context:

```bash
docker build \
  -f python/samples/04-hosting/foundry-hosted-agents/responses/06_hyperlight_codeact/Dockerfile \
  -t <acr>.azurecr.io/<repo>:<tag> \
  python/
```

Then push to your ACR and create a new Foundry hosted-agent version against
the image as described in the parent README.
