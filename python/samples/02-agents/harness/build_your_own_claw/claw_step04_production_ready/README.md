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
> `ResponsesHostServer` enters a **new factory-created agent per request**;
> `console_app.py` and `evals.py` do it explicitly with
> `async with agent:`.

> **The hosted agent's managed identity needs the `Foundry User` role.** This is the single most
> likely reason a Toolbox skill fails to load, and the failure actively misleads you: connecting to
> the toolbox and **discovering** skills both succeed (`skill://index.json` is toolbox metadata, which
> needs no role), so the skill is advertised to the model exactly as expected. Only the first
> `load_skill` fails — with `McpError('Failed to read resource.')` — because reading a skill's *body*
> dereferences the project-level skill resource, which does require the role. The toolbox answers
> with a bare JSON-RPC `-32603` and no `data`, so nothing in the error names the cause.
>
> Obtain the hosted managed identity's principal ID from the platform/resource
> configuration when granting the role. Startup diagnostics log only which
> variables are present, not identity/session/call values or tokens.
>
> ```bash
> az role assignment create --assignee-object-id <agent-identity-object-id> \
>   --assignee-principal-type ServicePrincipal --role "Foundry User" \
>   --scope /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>
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

The hosted version **disables file access and shell** on the container. In a
shared, hosted environment, arbitrary filesystem/shell access is a
data-exfiltration and tampering risk, and the local confirmations vault does not
exist there. Background research and Monty CodeAct remain enabled. An external
`file_access_store` must enforce trusted user/sandbox access before it can be
enabled; using a Blob Storage backend alone is not an authorization boundary.

File memory **stays enabled** when hosted, but its store has to move. The harness writes file memory
to `{cwd}/agent-file-memory` by default, and the deployed code directory (`/app`) is mounted
**read-only** on Foundry hosted agents, so the default directory fails. `hosted.py` therefore passes a
`FileSystemAgentFileStore` rooted at
`$HOME/.claw/agent-file-memory/<trusted-user-and-sandbox-hash>`, which is writable.
The hash comes from `FoundryRequestScope.storage_key`; hosted scope validation
uses the configured sandbox plus trusted user/call IDs, never a caller-selected
conversation or MAF session ID. File memory is **sandbox-specific**, unlike the
intentional user-wide sharing in the
[Foundry Memory sample](../../../../04-hosting/foundry-hosted-agents/responses/foundry_memory/).

`ResponsesHostServer(agent=create_agent, history_source="agent_server")` builds
new clients, Toolbox/skills providers, CodeAct and harness providers for each
request. The sample injects its own context-managed client into
`build_claw_agent`, leaving ownership of supplied/shared clients elsewhere
unchanged. That client closes only its own model/project transports and
credential; it captures the current platform call ID, not an earlier caller's.
History/approval state is persisted by the host, not retained on provider
instances. Local hosts keep their original builder defaults.

Request-lifetime middleware releases only this agent's background-provider
tasks for the active MAF session, in a `finally` path on success, failure or
cancellation. An idempotent cleanup hook on the outer stream also handles a
stream closed **before its first update**, while the iterator's `finally`
handles partial consumption and run errors. Outstanding research is cancelled
and joined before the request's transports close, using the provider's finite
**30-second** default. A child that ignores
cancellation is abandoned and logged when that bound expires, so it cannot
hold transport teardown open indefinitely. Complete/collect research within a
turn; unfinished runtime tasks cannot be resumed by a later factory-created
agent. Cleanup failure is logged without identity values and does not replace
an existing run failure.

Local runs use `AzureCliCredential` and are single-user development only.
Hosted runs use managed identity; project/Toolbox/Purview permissions and
resources require separate configuration. The unrelated Telegram sample also
requires externally configured Telegram/Key Vault credentials. None of those
credential-gated behaviors or deployments is proven by an offline smoke check.

### File-memory capacity and retention

SDK limits are opt-in: omitted `max_file_bytes`, `max_files`, and `max_total_bytes`
remain unlimited, and `FileMemoryProvider` without a retention manager keeps its existing
behavior. Retention currently supports the builtin filesystem store; customized backends
continue using the existing interface and are rejected if retention is explicitly enabled.
The hosted sample supplies finite limits and one server-owned
`FileMemoryRetentionManager` shared by all request-owned stores.

| Environment variable | Initial default | Meaning |
| --- | --- | --- |
| `CLAW_FILE_MEMORY_MAX_FILE_BYTES` | `1048576` (1 MiB) | Maximum stored file / whole-file read bytes |
| `CLAW_FILE_MEMORY_MAX_FILES` | `100` | Regular files under each trusted user/sandbox root |
| `CLAW_FILE_MEMORY_MAX_TOTAL_BYTES` | `10485760` (10 MiB) | Combined content bytes under each root |
| `CLAW_FILE_MEMORY_SHARED_MAX_BYTES` | `268435456` (256 MiB) | Shared contents, control metadata, and atomic-copy reserve |
| `CLAW_FILE_MEMORY_RETENTION_SECONDS` | `2592000` (30 days) | Initial idle lifetime for a new managed area; `none` initially disables TTL |
| `CLAW_FILE_MEMORY_SWEEP_INTERVAL_SECONDS` | `300` (5 minutes) | Server-driven cleanup interval, including when there are no requests |

These are example starting points, not universal deployment recommendations. Numeric values
must be positive integers; invalid configuration fails instead of disabling protection.
Root limits count existing files, descriptions, and `memories.md`, so `max_files` does not mean
that many user-visible memories. Bytes count UTF-8 content, not filesystem allocation.
The shared budget covers all roots and `.retention` control files; it reserves one staging
file and the size of the largest file for an atomic replacement. Filesystem allocation,
external writers, and unrelated storage are outside these limits. Reducing a budget does
not delete unexpired data. New growth is refused; request registration still requires
space for its protection token, and index repair may require additional capacity.

Retention applies to a logical memory: its body, optional description, and index entry.
Successful body reads, edits, and actual grep matches renew that memory. Listing,
unmatched search, index injection, and background scanning do not renew every memory.
Expired memories disappear from read/list/search/index before the next physical cleanup.
GC deletes eligible bodies and descriptions still unreferenced by other bodies; it only
prunes empty directories. Existing unregistered files stay readable and count toward
capacity, but are not enrolled or deleted by reading/scanning. A successful overwrite
starts their managed lifetime.

`.retention/policy.json` records the shared policy; per-root versioned manifests use hashed
record identifiers rather than filenames or identity values. This directory is host-owned
and must not be exposed through file access, shell, or custom tools. The provider rejects
overlapping filesystem `FileAccessProvider` roots. Every writer sharing the managed area
must use the manager with identical shared limits and consistent per-root limits;
direct store writes, older workers without management, multi-host
deployment, and network filesystems do not provide these guarantees. File locks coordinate
local processes and release after process death. Fixed coordination lock files stay in place.

The host keeps request protection through the full run and stream consumption/close.
GC skips scopes with an active request. That request can still use records that were valid
when it began; new requests cannot revive an expired record by reading it. Empty scopes
are reclaimed after their requests end. An existing root quota-lock marker is retained.

A normal restart loads the stored TTL policy and preserves deadlines. The TTL environment
value initializes a new area only; change an existing policy explicitly:

```python
# Use the same host-owned manager/directory as the server.
await retention.set_retention(None)         # disable expiration; retain metadata
await retention.set_retention(30 * 86400)   # explicitly resume with a complete new TTL
```

While disabled, reads remain available without renewal and TTL GC deletes no memories;
cleanup of dead request-protection markers continues.
Resuming grants still-present, registered `ready` records a complete lifetime from resume.
Repeated same-value calls do nothing. Changing one positive TTL to another affects new
writes and subsequent successful uses, not all existing deadlines. Deleted records cannot
be restored; interrupted updates/deletions are not revived by resuming.

Content, description, index, and manifest are not one filesystem transaction. Managed
files use staged atomic replacement; an interrupted update remains protected from expiry.
Failures after content changes report partial completion. Unknown/corrupt metadata is
preserved and management for that scope stops. Operators inspect current content and then
explicitly confirm interrupted updates with `await retention.repair(store)`; this rebuilds
the index and starts a fresh lifetime, without claiming to recover the original operation.
Pending deletions remain deletions and GC retries interrupted I/O. If a rebuilt index would
exceed capacity, GC removes the stale index and completes confirmed deletion; the provider
reconstructs its index projection on reads when capacity permits. Explicit update repair may
still need additional capacity. Maintenance does not bypass file or shared quotas.

The existing description naming replaces extensions, so `notes.md` and `notes.txt` share
`notes_description.md`. Descriptions retain this existing last-write-wins behavior; cleanup
preserves a sidecar while any other existing body still references it. Use distinct stems
when memories need independent descriptions.

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
