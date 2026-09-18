# ClawAgent.Hosted

ASP.NET host that serves the shared claw through the Foundry Responses hosting APIs.

The host is deliberately thin:

```csharp
var builder = WebApplication.CreateBuilder(args);

// Wires up the Responses API host for the agent and auto-applies OpenTelemetry.
builder.Services.AddFoundryResponses(build.Agent);

var app = builder.Build();

// The endpoint that live Foundry calls.
app.MapFoundryResponses();

// Contributor-only: local REPL route shape. Not used in production.
app.MapDevTemporaryLocalAgentEndpoint();

app.Run();
```

## Observability comes for free

No exporter wiring is required. `AddFoundryResponses` automatically wraps the agent with
`OpenTelemetryAgent`, and the Foundry hosting runtime (`Azure.AI.AgentServer.Core`'s
`AddAgentHostTelemetry`) registers the OTLP exporter pipeline. When hosted, Foundry injects
`APPLICATIONINSIGHTS_CONNECTION_STRING` automatically, so traces, metrics, and logs flow to
Application Insights with no configuration.

To capture prompt and response content in traces (off by default), set:

```bash
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true
```

## File and shell access are disabled here

The hosted build turns **file access and shell off**:

```csharp
await using ClawAgentBuild build = await ClawAgentFactory.CreateAsync(new ClawAgentFactoryOptions
{
    // ...
    EnableFileAccess = false,
    EnableShell = false,
});
```

Why: in a shared, hosted container, giving the model arbitrary read/write access to the filesystem, or
letting it run shell commands, is a serious security risk — data exfiltration, tampering, and
persistence — even behind a deny-list. The local confirmations vault the shell operates on doesn't
exist in the hosted environment anyway. If you enable either capability on a hosted container, treat it
as a production security decision and scope it tightly.

If you genuinely need file access when hosted, prefer supplying an **external `AgentFileStore`** (for
example, one backed by Azure Blob Storage) rather than the container disk:

```csharp
await using ClawAgentBuild build = await ClawAgentFactory.CreateAsync(new ClawAgentFactoryOptions
{
    // ...
    EnableFileAccess = true,
    FileStore = new MyBlobAgentFileStore(blobContainerClient),
});
```

## CodeAct runs on LocalCodeAct here, not Hyperlight

The local hosts give the model a **Hyperlight**-backed CodeAct sandbox, which runs guest code in a
VM-isolated micro-sandbox. That needs a hypervisor (KVM) and FUSE — neither of which an unprivileged
Foundry hosted container exposes — so the Hyperlight provider can't initialize its sandbox when
hosted, and the agent never becomes ready.

The hosted build instead supplies a **`LocalCodeActProvider`**, which runs the generated Python in a
child process and relies on the hosted container itself as the isolation boundary:

```csharp
await using ClawAgentBuild build = await ClawAgentFactory.CreateAsync(new ClawAgentFactoryOptions
{
    // ...
    EnableFileAccess = false,
    EnableShell = false,

    // Hyperlight needs a hypervisor + FUSE the hosted container lacks; LocalCodeAct relies on the
    // container as the sandbox. Override the interpreter with LOCAL_CODEACT_PYTHON if needed.
    CodeActProvider = new LocalCodeActProvider(
        Environment.GetEnvironmentVariable("LOCAL_CODEACT_PYTHON") ?? "python3"),
});
```

> **Security:** `LocalCodeAct` is not itself a sandbox — it executes model-generated Python in a child
> process. Only deploy it to an externally sandboxed environment such as a Foundry hosted-agent
> container. To turn CodeAct off entirely instead, set `EnableCodeAct = false`.

## Run locally

```bash
cd dotnet/samples/02-agents/Harness/BuildYourOwnClaw/Claw_Step04_ProductionReady/ClawAgent.Hosted
dotnet run
```

## Deploy to Foundry (container path)

This project deploys as a **container image** (not Foundry's source-code/zip path).

The project uses `ProjectReference` to sibling and
framework sources (`ClawAgent`, `Microsoft.Agents.AI.Foundry`, `.Foundry.Hosting`,
`.LocalCodeAct`) and the repo's Central Package Management (`dotnet/Directory.Packages.props`).

Because the ProjectReferences point outside this folder, a standard in-container `dotnet publish`
can't resolve them. So the flow is **two explicit steps**: publish locally first, then build/deploy
the image (this is what [`Dockerfile`](./Dockerfile) expects — it just
`COPY`s the pre-published `out/`).

**1. (First time only) initialize azd in container mode** (writes a `docker`-based `azure.yaml`):

```bash
azd ai agent init -m agent.manifest.yaml --deploy-mode container
```

`azd init` provisions (or reuses) a **container registry** and records it in the
`AZURE_CONTAINER_REGISTRY_ENDPOINT` environment variable, so you don't need to configure a registry
manually — azd pushes the built image there using this project's [`Dockerfile`](./Dockerfile)
automatically.

By default azd builds the image **remotely in Azure Container Registry**, so you don't need local
Docker. Set `remoteBuild: false` under the `docker:` options in `azure.yaml` to build locally
(requires Docker Desktop).

**2. Build and publish the app separately** (on your machine, inside the full repo, so the
ProjectReferences and package versions resolve). Target the container runtime (glibc x64):

```bash
cd dotnet/samples/02-agents/Harness/BuildYourOwnClaw/Claw_Step04_ProductionReady/ClawAgent.Hosted
dotnet publish -c Release -f net10.0 -r linux-x64 --self-contained false -o out
```

This produces `out/ClawAgent.Hosted.dll` and its dependencies. `out/` is what
`Dockerfile` copies — you must run this step **before** every image build/deploy.

**3. Grant the Foundry workspace identity `AcrPull` on the registry.** azd pushes the image, but the
hosted agent runtime pulls it using the Foundry **project's** system-assigned managed identity. That
identity needs `AcrPull` on your registry, or the deploy fails with *"Container registry
authentication failed … verify the workspace managed identity has AcrPull permissions"*:

```bash
# Get the project's system-assigned managed identity principal id:
PRINCIPAL_ID=$(az resource show \
  --ids "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<foundry-account>/projects/<project-name>" \
  --query identity.principalId -o tsv)

# Grant AcrPull on the registry:
az role assignment create \
  --role AcrPull \
  --assignee-principal-type ServicePrincipal \
  --assignee-object-id "$PRINCIPAL_ID" \
  --scope /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ContainerRegistry/registries/<registry-name>
```

> RBAC changes can take a minute or two to propagate before the deploy can pull the image.

**4. Deploy:**

```bash
azd up      # first deploy: provisions resources, builds the image, creates the agent version
# or, once provisioned (remember to re-run step 2 first so out/ is fresh):
azd deploy
```

**Test the image locally first (optional but recommended):**

```bash
# after step 2:
docker build -t personal-finance-claw .
docker run --rm -p 8088:8088 --env-file .env personal-finance-claw
# in another shell — should return HTTP 200:
curl -i http://localhost:8088/readiness
```

> **Non-interactive note:** the sample helpers prompt on the console for missing settings, which would
> block a non-interactive container. The image sets `AF_DEMO_NONINTERACTIVE=1` (and `az`-style hosts
> have redirected stdin) so startup never blocks. Provide real values via the `env:` map in
> `azure.yaml` or the container's environment. See the
> [container deployment guide](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent).
