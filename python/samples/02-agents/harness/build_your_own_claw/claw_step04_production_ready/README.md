# Claw Step 04 — Production-ready

This folder restructures the Step 03 claw into a shared agent module plus thin hosts. It is also a
self-contained Foundry deployment package: Foundry uses code (ZIP) deployment for Python hosted
agents and uploads this folder only.

- `agent.py` — `build_claw_agent(...)` builds the full Step 03 claw and adds opt-in Purview chat middleware.
- `console_app.py` — local interactive Textual console with OpenTelemetry provider setup.
- `hosted.py` — Foundry Hosted Agent entry point using `ResponsesHostServer`.
- `evals.py` — local finance checks plus optional Foundry evaluators.
- `requirements.txt` — packages installed into the hosted deployment.
- `.agentignore` — files excluded from the uploaded package (caches, `.env`, azd tooling files).
- `skills/` and `subprocess_script_runner.py` — local copies so the folder is a self-contained
  package (the parent sample folder is outside the upload and cannot be reached from the container).

## Environment

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://your-project.services.ai.azure.com/api/projects/your-project"
export FOUNDRY_MODEL="your-local-model-deployment"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="your-hosted-model-deployment"
```

Optional:

```bash
export TOOLBOX_MCP_SERVER_URL="https://.../mcp?api-version=v1"
export PURVIEW_CLIENT_APP_ID="your-purview-app-client-id"
export ENABLE_CONSOLE_EXPORTERS="true"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
```

> **Why `TOOLBOX_MCP_SERVER_URL` and not `FOUNDRY_TOOLBOX_MCP_SERVER_URL`?** Foundry hosted agents
> reserve the `FOUNDRY_*` (and `AGENT_*`) prefix for platform-injected variables such as
> `FOUNDRY_PROJECT_ENDPOINT`. A custom variable using that prefix does not reach the container, so
> the toolbox skills would silently fail to load when deployed. Keep this one unprefixed.

> **How the toolbox is wired.** `agent.py` uses `FoundryToolbox` (from `agent_framework.foundry`)
> with `load_tools=False`, so only the toolbox's Agent Skills are surfaced, and passes it to the
> agent via `tools=` — that is what connects its MCP session. `MCPSkillsSource` then reads skills
> from `toolbox.session`, aggregated with the local file skills. `FoundryToolbox` authenticates each
> request and forwards the platform's per-request `x-agent-foundry-call-id`. See
> [`04-hosting/foundry-hosted-agents/responses/foundry_toolbox_mcp_skills`](../../../../04-hosting/foundry-hosted-agents/responses/foundry_toolbox_mcp_skills)
> for the minimal version of this pattern. Hosted runs connect the toolbox because
> `ResponsesHostServer` enters the agent; `console_app.py` and `evals.py` do it explicitly with
> `async with agent:`.

> **The hosted agent's managed identity needs the `Foundry User` role.** This is the single most
> likely reason a Toolbox skill fails to load, and the failure actively misleads you: connecting to
> the toolbox and **discovering** skills both succeed (`skill://index.json` is toolbox metadata, which
> needs no role), so the skill is advertised to the model exactly as expected. Only the first
> `load_skill` fails — with `McpError('Failed to read resource.')` — because reading a skill's *body*
> dereferences the project-level skill resource, which does require the role. The toolbox answers
> with a bare JSON-RPC `-32603` and no `data`, so nothing in the error names the cause.
>
> The container logs the identity to grant it to at startup:
>
> ```
> Agent managed identity (grant it the Foundry User role): <client-id>
> ```
>
> ```bash
> az role assignment create --assignee-object-id <agent-identity-object-id> \
>   --assignee-principal-type ServicePrincipal --role "Foundry User" \
>   --scope /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>
> ```
>
> Resolve the object id with `az ad sp list --filter "startswith(displayName,'<account>')" -o table`
> (the agent's `…-AgentIdentity` entry), and verify with
> `az role assignment list --assignee <object-id> --all`.
>
> **Allow for RBAC propagation.** A grant can take several minutes to take effect. Retesting
> immediately can still fail with the identical error, which makes it easy to wrongly conclude the
> role was not the problem. If the first retest fails, wait and try again before looking elsewhere.

## Run locally

```bash
uv run --prerelease=allow python/samples/02-agents/harness/build_your_own_claw/claw_step04_production_ready/console_app.py
```

> **Why `--prerelease=allow`?** These entry points depend on `agent-framework-foundry-hosting`
> (it provides `FoundryToolbox`), which is currently a prerelease. Without the flag uv refuses to
> resolve the PEP 723 dependency block and the run fails before it starts.

## Host with Foundry

```bash
uv run --prerelease=allow python/samples/02-agents/harness/build_your_own_claw/claw_step04_production_ready/hosted.py
```

The hosted version **disables file access and shell** on the container. In a shared, hosted environment, giving the model arbitrary read/write access to the container filesystem or letting it run shell commands is a serious security risk (data exfiltration, tampering, persistence), and the local confirmations vault the shell operates on doesn't exist there. Background agents and Monty CodeAct (alpha) remain enabled. If you need file access when hosted, pass an external `file_access_store` (for example, one backed by Azure Blob Storage) instead of the container disk.

File memory **stays enabled** when hosted, but its store has to move. The harness writes file memory
to `{cwd}/agent-file-memory` by default, and the deployed code directory (`/app`) is mounted
**read-only** on Foundry hosted agents, so the default directory fails. `hosted.py` therefore passes a
`FileSystemAgentFileStore` rooted at `~/.claw/agent-file-memory`, which is writable.

### Deploy to Foundry

```bash
cd python/samples/02-agents/harness/build_your_own_claw/claw_step04_production_ready
azd ai agent init -m agent.manifest.yaml --entry-point hosted.py
azd deploy
```

Foundry deploys this agent with **code (ZIP) deployment** — the default for Python hosted agents.
It uploads this folder, installs `requirements.txt`, and runs a Python entry point. Which file runs
is set by `codeConfiguration.entryPoint` in the generated `azure.yaml` and defaults to `main.py`, so
you must point it at `hosted.py`. We therefore pass `--entry-point hosted.py` to
`azd ai agent init`. The deploy packages this folder only, so `skills/` and
`subprocess_script_runner.py` are copied in here, making the folder a self-contained package.

## Run evals

```bash
uv run --prerelease=allow python/samples/02-agents/harness/build_your_own_claw/claw_step04_production_ready/evals.py
```

Local evals use `LocalEvaluator` custom checks. When `FOUNDRY_PROJECT_ENDPOINT` is set, the sample also runs `FoundryEvals` with relevance and coherence.

> **Why the evals auto-approve skill scripts.** `evals.py` passes `auto_approve_skill_scripts=True`
> to `build_claw_agent`. The valuation skill's instructions tell the agent to run
> `scripts/valuation_metrics.py`, and `run_skill_script` requires approval by default — so an
> unattended run would stop at an approval request and the valuation check would score that instead
> of a real answer. The flag is eval-only and scoped to the skill tools: `place_trade`, the shell,
> and file writes keep their normal approval behavior.

> **Foundry evals permissions.** The `FoundryEvals` step uploads the eval items as a temporary
> dataset to the storage account backing your Foundry project. The identity running the evals — your
> `az login` user for local runs, or the project's managed identity when it reaches storage via
> Entra ID — needs the **Storage Blob Data Contributor** role on that storage account, plus an
> appropriate project role (for example **Azure AI User**). Without the blob role the run fails at
> the dataset upload with `UnauthorizedUserAction` (`POST .../assetstore/v1.0/temporaryDataReference`)
> even though the local evals pass. See
> [Troubleshoot evaluation and observability issues](https://learn.microsoft.com/azure/foundry/observability/how-to/troubleshooting).

## Observability and Purview

The **local** hosts (`console_app.py`, `evals.py`) call `configure_otel_providers()` from `agent_framework.observability`, which honors `ENABLE_INSTRUMENTATION`, `ENABLE_SENSITIVE_DATA`, `ENABLE_CONSOLE_EXPORTERS`, and OTLP endpoint environment variables.

The **hosted** host (`hosted.py`) wires no exporters: Agent Framework instrumentation is on by default and the Foundry hosting runtime collects and exports telemetry. Foundry injects `APPLICATIONINSIGHTS_CONNECTION_STRING` when deployed; set `ENABLE_SENSITIVE_DATA=true` to include prompt/response content. Because the exporters are Foundry-managed, run the hosted host with `azd ai agent run` to see telemetry.

Purview is opt-in. When `PURVIEW_CLIENT_APP_ID` is set, `agent.py` creates `InteractiveBrowserCredential(client_id=...)` and attaches `PurviewChatPolicyMiddleware(..., PurviewSettings(app_name="Claw"))` to `FoundryChatClient`. Otherwise it prints a note and runs without policy middleware.
