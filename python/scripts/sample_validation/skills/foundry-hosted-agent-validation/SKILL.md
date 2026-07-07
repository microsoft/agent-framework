---
name: foundry-hosted-agent-validation
description: >
  Step-by-step process for validating a Python Foundry hosted agent sample
  (under python/samples/04-hosting/foundry-hosted-agents/) end to end — running
  it locally (native runtime and `azd ai agent run`) and after deploying it to
  an Azure AI Foundry project with `azd`. Use this when asked to validate, smoke
  test, or verify a hosted agent sample works locally and/or deployed, or when
  deploying one of these samples to Foundry.
license: MIT
compatibility: Works with any model that supports tool use.
metadata:
  author: agent-framework-samples
  version: "1.0"
---

# Validating a Foundry Hosted Agent Sample

A hosted agent sample is "validated" when it passes **three** independent
checks, plus cleanup:

1. **Local, native runtime** — run the sample's own entry point
   (`python main.py`) and invoke it over HTTP.
2. **Local, via `azd ai agent run`** — the `azd` local dev loop.
3. **Deployed** — `azd deploy` to Foundry, then invoke the hosted agent.

Each check must succeed for **single-turn** and **multi-turn** (session /
`previous_response_id`) conversation. Always end with **cleanup** (delete the
deployed agent, remove the temp `azd` project, restore the sample dir).

> Read the sample's own `README.md` and the parent
> `.../foundry-hosted-agents/README.md` first — they define the run/deploy
> commands and any sample-specific payload. This skill captures the process and
> the non-obvious gotchas the READMEs don't.

---

## Automated script

[`scripts/validate_hosted_agent.sh`](scripts/validate_hosted_agent.sh) runs all
three phases (and cleanup) non-interactively — use it for a full pass, and read
the phases below to interpret failures or validate a non-`responses` sample by
hand. Run `--help` for the full dependency list and options.

```bash
# Full validation of the responses/01_basic sample (default sample dir):
python/scripts/sample_validation/skills/foundry-hosted-agent-validation/scripts/validate_hosted_agent.sh \
  --project-endpoint "https://<account>.services.ai.azure.com/api/projects/<project>" \
  --model "<real-deployed-model>" \
  --acr-endpoint "<acr-login-server>"

# Local-only (skip deploy), or point at another sample:
python/scripts/sample_validation/skills/foundry-hosted-agent-validation/scripts/validate_hosted_agent.sh --skip-deploy \
  --sample-dir python/samples/04-hosting/foundry-hosted-agents/responses/02_tools \
  --project-endpoint "..." --model "..."
```

Inputs may also come from env vars (`FOUNDRY_PROJECT_ENDPOINT`,
`AZURE_AI_MODEL_DEPLOYMENT_NAME`, `FOUNDRY_PROJECT_ID`,
`AZURE_CONTAINER_REGISTRY_ENDPOINT`). Phase flags: `--skip-native`,
`--skip-azd-local`, `--skip-deploy`; `--no-cleanup`/`--keep-agent` to inspect
afterward. The script encodes every gotcha below (model template fix,
pre-existing-agent removal, ACR reuse, port/temp cleanup).

---

## Inputs you need before starting

Gather these (ask the user if not provided):

- **Foundry project endpoint**, e.g.
  `https://<account>.services.ai.azure.com/api/projects/<project>`.
- **Foundry project resource id** (for non-interactive `azd ai agent init`):
  `/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>`.
  Find it with `az cognitiveservices account list` + the project name.
- **A real, deployed model name** in that project (e.g. `gpt-4.1-mini`). This is
  often **different** from the model id in `agent.manifest.yaml` — the actual
  deployment name wins.
- **An existing ACR to reuse** for deployment (login server, e.g.
  `myacr.azurecr.io`). Reusing one avoids `azd provision` creating resources.
- Whether a like-named agent **already exists** in the project (remove it first
  for a clean validation — see below).

## Tooling / auth

- `az` (logged in: `az login`) and `azd` (logged in: `azd auth login`).
- `azd` **agents extension**: `azd extension list` should show
  `azure.ai.agents`; install with `azd extension install azure.ai.agents`.
- `uv` for the native-Python local run. **`python` need not be on PATH** — `uv`
  and `azd ai agent run` provision their own interpreter.
- Docker is **not** required when you reuse an ACR (`remoteBuild: true` builds
  in ACR Tasks).

---

## Phase 0 — Understand the sample

A responses/invocations sample folder typically contains:
`main.py` (entry point + `ResponsesHostServer`/`InvocationsHostServer`),
`agent.manifest.yaml` (used by `azd ai agent init`), `agent.yaml` (the deployed
agent definition), `requirements.txt`, `Dockerfile`, `.env.example`.

Note the **protocol** (`responses` or `invocations`) from `agent.yaml` /
manifest — it changes the invoke command (`--protocol invocations`) and the HTTP
path (`/responses` vs the invocations route).

---

## Phase 1 — Local validation, native runtime (Python)

Run from the sample directory.

```bash
uv venv .venv --python 3.12          # 3.12 matches the sample Dockerfile
uv pip install --python .venv/... -r requirements.txt
```

Create `.env` from `.env.example` with the **real** values:

```
FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
AZURE_AI_MODEL_DEPLOYMENT_NAME="<real-deployed-model>"
```

Start the server (`python main.py`) — it listens on `http://localhost:8088`.
`main.py` uses `DefaultAzureCredential`, so `az login` must be current.

Invoke (single turn), capture the returned `response_id`, then reuse it for a
follow-up turn to confirm memory:

```bash
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "My name is Tao. Remember it."}'
# take response_id from the JSON, then:
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "What is my name?", "previous_response_id": "<response_id>"}'
```

PowerShell: use `Invoke-WebRequest -Uri http://localhost:8088/responses -Method POST -ContentType application/json -Body '...'`.

**Pass:** HTTP 200, non-empty `output[].content[].text`, and the second turn
recalls the name. Stop the server afterward.

---

## Phase 2 — Local validation via `azd ai agent run`

### Init the azd project (once)

Run in an **empty temp directory outside the repo** (short path avoids Windows
path-length issues, e.g. `C:\afval\<sample>`). Point `-m` at the **local**
manifest so it validates the working-tree sample:

```bash
azd ai agent init -m <path>/agent.manifest.yaml \
  --project-id "<project-resource-id>" \
  --model-deployment "<real-deployed-model>" \
  --agent-name "<agent-name-from-manifest>" \
  --no-prompt --force
```

`init` downloads the template into a **subfolder named after the agent**, so the
azd project root is `<tempdir>/<agent-name>/`. `cd` there for all later `azd`
commands.

> **Before init, remove any `.venv` you created in the sample dir** — `init`
> copies the entire manifest directory into `src/`. (`.venv` is excluded from
> deploy packaging by `.agentignore`/`.dockerignore`, so it is harmless but
> bloats/slows the copy.)

### Fix the model deployment name (critical — see Gotcha 1)

```bash
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "<real-deployed-model>"
```

### Run and invoke locally

```bash
azd ai agent run --no-inspector        # auto-creates a uv venv + installs deps; listens on :8088
azd ai agent invoke --local --new-session "My name is Tao. Remember it."
azd ai agent invoke --local "What is my name?"   # same session is reused automatically
```

**Pass:** both invokes return text; the second recalls the name (same
`Session:` id). Stop the `run` process afterward.

---

## Removing a pre-existing agent (do this before deploying)

`init` prints a warning if the agent name already exists in the project. To
delete it, note that **`azd ai agent delete`/`show` resolve the deployed agent
name from an azd env var, not from the positional argument.** The var is
`AGENT_{SERVICEKEY}_NAME`, where `SERVICEKEY` = the `azure.yaml` service name
uppercased with `-`/spaces → `_`.

Example for service `agent-framework-agent-basic-responses`:

```bash
azd env set AGENT_AGENT_FRAMEWORK_AGENT_BASIC_RESPONSES_NAME agent-framework-agent-basic-responses
azd ai agent delete <service-name> --force --no-prompt --output json
# -> {"object":"agent.deleted","name":"...","deleted":true}
```

(After a successful `azd deploy`, this var is set automatically, so later
`show`/`delete`/`invoke` work without setting it.)

---

## Phase 3 — Deploy and validate

### Reuse an existing ACR (avoid provisioning)

For an existing project + model, **do not run `azd provision`/`azd up`** — the
generated `azure.yaml` has a `deployments` block for the manifest's model
(often an auto-selected `GlobalProvisionedManaged` PTU SKU) that provision would
try to create (costly / quota failures). Instead reuse an ACR:

```bash
azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT <acr-login-server>   # e.g. myacr.azurecr.io
azd deploy
```

`azd deploy` fails with _"could not determine container registry endpoint"_ if
this is unset and no ACR is provisioned.

### Verify the deployed model env var, then invoke

```bash
azd ai agent show <agent-name> --output json   # check definition.environment_variables.AZURE_AI_MODEL_DEPLOYMENT_NAME
azd ai agent invoke <agent-name> --new-session "My name is Tao. Remember it."
azd ai agent invoke <agent-name> "What is my name?"
```

Use `--output raw` on invoke to see raw SSE events and any failure, e.g.:

```
event: response.failed
... "code": "DeploymentNotFound" ... 404 ...
```

`DeploymentNotFound` means the deployed `AZURE_AI_MODEL_DEPLOYMENT_NAME` points
at a model that isn't deployed → fix per Gotcha 1 and redeploy (creates a new
version).

**Pass:** agent reaches `status: active`, invoke returns text (not empty, no
`response.failed`), and multi-turn recalls the name.

---

## Cleanup (always)

- Delete the deployed agent: `azd ai agent delete <agent-name> --force --no-prompt`.
- Delete the temp `azd` project directory.
- Remove `.env`/`.venv` you created in the sample dir; confirm the sample dir is
  pristine (`git status --porcelain <dir>` is empty — `.env`/`.venv` are
  gitignored).
- Stop any leftover local server still holding port 8088:
  `Get-NetTCPConnection -LocalPort 8088 -State Listen` → `Stop-Process -Id <pid>`
  (Linux/macOS: `lsof -ti:8088 | xargs kill`). Stopping the shell may leave the
  child interpreter running.

---

## Gotchas (the parts that waste the most time)

1. **The deployed model name comes from `agent.yaml`, not the azd env.**
   `azd ai agent init` ignores `--model-deployment` in `--no-prompt` mode and
   writes the **manifest's** model id (e.g. `gpt-4.1-mini`) as a **literal** into
   both the azd env `AZURE_AI_MODEL_DEPLOYMENT_NAME` and the generated
   `src/<agent>/agent.yaml` env var. Local runs read the azd env (so
   `azd env set` fixes them), but **deployment injects `agent.yaml`'s value**.
   Fix by setting the generated `agent.yaml` env var to the template
   `value: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}` (what the repo sample already uses;
   `init` flattens it) **and** `azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME <real>`,
   then redeploy. A literal `value: <real-model>` also works.

2. **`azd ai agent delete/show` need the `AGENT_{SERVICEKEY}_NAME` env var** — a
   bare positional agent name is treated as the _service_ name and the deployed
   agent name is looked up from that env var (see "Removing a pre-existing
   agent").

3. **`azd provision`/`azd up` will try to create the manifest's model
   deployment** (from `azure.yaml`'s `deployments` block). Prefer `azd deploy`
   with a reused ACR when the project + model already exist.

4. **`python` on PATH is not required.** `uv venv` and `azd ai agent run`
   provision their own interpreter and install `requirements.txt`.

5. **`init` copies the whole manifest directory into `src/`.** Remove a local
   `.venv` from the sample dir first to keep the copy clean/fast.

6. **Port 8088 can stay bound after stopping the shell** — kill the interpreter
   by PID (see Cleanup).

---

## Success checklist

- [ ] Native local run: 200 + non-empty text + multi-turn recall.
- [ ] `azd ai agent run` local: text returned + session reused across invokes.
- [ ] Pre-existing agent removed (if any).
- [ ] `azd deploy` succeeds; agent `status: active`.
- [ ] `azd ai agent show` confirms `AZURE_AI_MODEL_DEPLOYMENT_NAME` = the real
      deployed model.
- [ ] Deployed invoke: text returned (no `response.failed`) + multi-turn recall.
- [ ] Cleanup done: agent deleted, temp project removed, sample dir pristine,
      port 8088 free.
