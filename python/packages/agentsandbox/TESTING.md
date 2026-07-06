# Testing `agent-framework-agentsandbox` locally

This walks through a full local end-to-end test of the agent-sandbox CodeAct
integration: a local Kubernetes cluster (kind) running the agent-sandbox
controller, plus a local Ollama model (no API key required).

> **Version requirement.** This integration needs agent-sandbox **v0.5.0 or
> newer** — the first release with the native async client (`AsyncSandboxClient`
> / `AsyncSandbox`) and the warm-pool claim API (`create_sandbox(warmpool=...)`),
> plus the per-sandbox headless Service the router relies on. The package's
> `pyproject.toml` pins `k8s-agent-sandbox[async]>=0.5.0`, and the steps below
> install the controller from the v0.5.0 release manifests (no source build).

The integration talks to the Pod through the **sandbox-router**. The async
client does not support `kubectl port-forward` tunnelling, so you run a
port-forward yourself and point the sample at it with
`SandboxDirectConnectionConfig`.

## Prerequisites

```bash
brew install kind kubectl
brew install --cask docker            # Docker engine must be running
brew install ollama
# uv is already installed at ~/.local/bin from building the package
```

Clone agent-sandbox (for the router source and the `SandboxTemplate` manifest)
and reference your local clone of the `agent-framework` repository:

```bash
git clone https://github.com/kubernetes-sigs/agent-sandbox.git
export AGENT_SANDBOX=$(pwd)/agent-sandbox
export AF=/path/to/agent-framework            # root of this repository
export AGENT_SANDBOX_VERSION=v0.5.0
```

---

## Step 1 — Create a kind cluster and install the controller + extensions

The **extensions** manifest is required — the integration claims from a
`SandboxWarmPool`.

```bash
kind create cluster --name agent-sandbox
kubectl apply -f "https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${AGENT_SANDBOX_VERSION}/manifest.yaml"
kubectl apply -f "https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${AGENT_SANDBOX_VERSION}/extensions.yaml"
kubectl -n agent-sandbox-system rollout status deploy --timeout=180s
```

---

## Step 2 — Build and load the sandbox-router image

The router ships as source (not a release image), so build it once and load it
into the cluster.

```bash
cd "$AGENT_SANDBOX/clients/python/agentic-sandbox-client/sandbox-router"
docker build -t sandbox-router:dev .
kind load docker-image sandbox-router:dev --name agent-sandbox
```

---

## Step 3 — Deploy the sandbox-router

Substitute the local image, force `imagePullPolicy: Never`, and drop to one
replica for a laptop.

```bash
cd "$AGENT_SANDBOX/clients/python/agentic-sandbox-client/sandbox-router"

sed -e 's|${ROUTER_IMAGE}|sandbox-router:dev|' \
    -e 's|# imagePullPolicy: Never|imagePullPolicy: Never|' \
    -e 's|replicas: 2|replicas: 1|' \
    sandbox_router.yaml | kubectl apply -n default -f -

# Allow unauthenticated access (see note below) and wait for the rollout.
kubectl -n default set env deploy/sandbox-router-deployment ALLOW_UNAUTHENTICATED_ROUTER=true
kubectl -n default rollout status deploy/sandbox-router-deployment --timeout=120s
```

> **Router authentication.** Recent `sandbox-router` builds refuse to start
> unless either `ROUTER_AUTH_TOKEN` is set (token-authenticated mode) or
> `ALLOW_UNAUTHENTICATED_ROUTER=true` is set (local/dev mode). The
> `k8s-agent-sandbox` Python SDK does not currently send an auth token, so the
> router must run in unauthenticated mode for the SDK — and therefore this
> integration — to reach it. We set `ALLOW_UNAUTHENTICATED_ROUTER=true` above.
> Without it the router pod enters `CrashLoopBackOff` and every request fails.
> (When the SDK gains token support, set `ROUTER_AUTH_TOKEN` instead and pass
> the matching token through the SDK.)

> Everything lives in the `default` namespace because the sample defaults to
> `namespace="default"`. Keep router, template, warm pool, and sandboxes there.

---

## Step 4 — Apply the SandboxTemplate and a SandboxWarmPool

The template defines the Pod spec; the warm pool references the template and is
what the SDK claims from. The sample defaults to a pool named
`python-sandbox-pool`.

```bash
cd "$AGENT_SANDBOX/clients/python/agentic-sandbox-client"

# Template (placeholders for name/namespace):
SANDBOX_TEMPLATE_NAME=python-sandbox-template \
SANDBOX_NAMESPACE=default \
  envsubst < python-sandbox-template.yaml | kubectl apply -f -

# Warm pool that references the template:
kubectl apply -f - <<'EOF'
apiVersion: extensions.agents.x-k8s.io/v1beta1
kind: SandboxWarmPool
metadata:
  name: python-sandbox-pool
  namespace: default
spec:
  replicas: 1                       # pre-warm one Pod; use 0 for purely on-demand
  sandboxTemplateRef:
    name: python-sandbox-template
EOF

kubectl -n default get sandboxtemplate,sandboxwarmpool
```

(No `envsubst`? `brew install gettext` or hand-edit the two placeholders.)

The template points at the public image
`us-central1-docker.pkg.dev/k8s-staging-images/agent-sandbox/python-runtime-sandbox:latest-main`.
Optionally pre-pull + load it so the first claim is not slowed by an in-cluster
pull:

```bash
docker pull us-central1-docker.pkg.dev/k8s-staging-images/agent-sandbox/python-runtime-sandbox:latest-main
kind load docker-image us-central1-docker.pkg.dev/k8s-staging-images/agent-sandbox/python-runtime-sandbox:latest-main --name agent-sandbox
```

---

## Step 5 — Port-forward the router

The async client connects via `SandboxDirectConnectionConfig`, so expose the
router on localhost in a **separate terminal** (keep it running):

```bash
kubectl -n default port-forward svc/sandbox-router-svc 8080:8080
```

---

## Step 6 — Start Ollama and pull a tool-capable model

```bash
ollama serve &                 # if not already running as a service
ollama pull qwen2.5            # solid function-calling; ~4.7GB
export OLLAMA_MODEL=qwen2.5
# export OLLAMA_HOST=http://localhost:11434   # default; only set if different
```

---

## Step 7 — Install the agent-framework workspace

```bash
cd "$AF/python"
export PATH="$HOME/.local/bin:$PATH"     # uv
uv sync --all-packages --all-extras --dev --prerelease=if-necessary-or-explicit
```

The `agentsandbox` package depends on `k8s-agent-sandbox[async]>=0.5.0`, so this
pulls the async-capable SDK from PyPI.

---

## Step 8 — Run the sample

```bash
cd "$AF/python"
export OLLAMA_MODEL=qwen2.5
uv run --no-sync python \
  samples/02-agents/context_providers/agentsandbox_codeact/agentsandbox_codeact.py
```

Optional overrides:

```bash
export AGENT_SANDBOX_WARMPOOL=python-sandbox-pool
export AGENT_SANDBOX_NAMESPACE=default
export AGENT_SANDBOX_ROUTER_URL=http://localhost:8080
```

---

## Step 9 — What success looks like

- A `SandboxClaim` / `Sandbox` / Pod appears while the sample runs:

  ```bash
  kubectl -n default get sandboxclaim,sandbox,pod
  ```

- The console shows the model emitting an `execute_code` block, the sandbox
  returning stdout, and the agent summarizing — for both prompts. Turn 1 writes
  `/app/fib.txt`; turn 2 reads it back in a *separate* `execute_code` call,
  proving the Pod's filesystem persists across calls.

- When the script exits (the `async with` block closes), the SandboxClaim and
  its Pod are deleted automatically. The `shutdown_after_seconds=30*60` in the
  sample is a controller-side safety net if the process is killed.

> **`pip install` inside the sandbox.** The reference `python-runtime-sandbox`
> image runs as a non-root user whose `HOME` (`/`) is read-only, so a plain
> `pip install <pkg>` fails with a permission error while trying to write
> `/.local` or `/.cache`. The working directory `/app` *is* writable, so install
> into a path under it and add that path to `sys.path` — for example
> `pip install --target=/app/.pkgs <pkg>`, then
> `sys.path.insert(0, "/app/.pkgs")`. Packages installed this way persist on the
> Pod across `execute_code` calls (that location survives because the Pod is
> long-lived), which is one of the advantages of this backend. A runtime image
> with a writable `HOME` would let a plain `pip install` work too; that is an
> image choice, not a limitation of the integration.

Run the package unit tests too (no cluster needed):

```bash
cd "$AF/python"
uv run --no-sync pytest packages/agentsandbox/tests -v
```

### Optional: sanity-check the cluster with the SDK's own e2e first

If the sample fails, isolate the cluster from the integration by running the
SDK's own test (no LLM, none of this package's code):

```bash
cd "$AGENT_SANDBOX/clients/python/agentic-sandbox-client"
python3 -m venv /tmp/agentsbx-sdk && source /tmp/agentsbx-sdk/bin/activate
pip install -q -e .
python test_client.py --namespace default --warmpool-name python-sandbox-pool
```

---

## Cleanup

```bash
kubectl -n default delete sandboxwarmpool/python-sandbox-pool --ignore-not-found
kubectl -n default delete sandboxtemplate/python-sandbox-template --ignore-not-found
kubectl -n default delete deploy/sandbox-router-deployment svc/sandbox-router-svc --ignore-not-found

# Then drop the whole cluster:
kind delete cluster --name agent-sandbox
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Router pod in `CrashLoopBackOff`; logs say `ROUTER_AUTH_TOKEN must be set` | The router refuses to start unauthenticated by default. Set `ALLOW_UNAUTHENTICATED_ROUTER=true` on the deployment (Step 3) for local/dev, or `ROUTER_AUTH_TOKEN` for token mode. The SDK does not send a token yet, so it needs the router in unauthenticated mode. |
| `pip install` fails with `Permission denied: '/.local'` inside the sandbox | The runtime image's `HOME` is read-only. Install under `/app` instead: `pip install --target=/app/.pkgs <pkg>` then `sys.path.insert(0, "/app/.pkgs")`. See the note in Step 9. |
| `ValueError: connection_config is required` | The async client needs `SandboxDirectConnectionConfig` / `SandboxGatewayConnectionConfig` / `SandboxInClusterConnectionConfig`. Local-tunnel is not supported by the async client. |
| `502 Bad Gateway` / `Name or service not known` from the router | Controller older than v0.5.0 — the per-sandbox headless Service is missing. Install the v0.5.0 (or newer) release manifests (Step 1). |
| `create_sandbox() got an unexpected keyword 'warmpool'` | SDK older than 0.5.0. Confirm with `uv run --no-sync python -c "import inspect; from k8s_agent_sandbox import AsyncSandboxClient; print(inspect.signature(AsyncSandboxClient.create_sandbox))"`. |
| `SandboxWarmPoolNotFoundError` | The warm pool is missing or in another namespace. It must match the provider's `namespace` (`default`). |
| Claim never becomes Ready | First image pull is slow. Pre-pull + load the runtime image (end of Step 4), or raise `sandbox_ready_timeout`. |
| Model never calls `execute_code` | The Ollama model is too weak at tool calling. Use `qwen2.5` or `llama3.1:8b`. |
| `kubectl` talks to the wrong cluster | `kubectl config use-context kind-agent-sandbox`. |
