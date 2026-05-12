# Hosted-Files

A hosted agent that demonstrates **two distinct file knowledge sources** through scoped, security-hardened tools:

- **Bundled files** (image-baked) — files the author packages with the agent at build time. Live at `/app/resources/` inside the container, copied from this project's [`resources/`](./resources/) folder via the csproj `<Content Include="resources\**\*" CopyToOutputDirectory="PreserveNewest" />` rule.
- **Session files** (per-session `$HOME` volume) — files the user uploads at runtime via the alpha `Azure.AI.Projects.AgentSessionFiles` SDK. Live at `$HOME` inside the per-session container. The Foundry platform sets `HOME=/home/session` by default and roots the session-files API there per [`container-image-spec.md` line 172](https://github.com/microsoft/foundrysdk-specs/blob/main/specs/agents/hosted_agents/container-spec/docs/container-image-spec.md): *"If you use the session files API, `$HOME` is also the base path for those operations; any paths given in those API endpoints will be relative to `$HOME`."*

## Tool surface

Each source is exposed via its own tool pair, rooted at its own directory. The model picks by intent.

| Tool | Source | Root |
|------|--------|------|
| `ListBundledFiles` | Bundled (image-baked) | `/app/resources/` |
| `ReadBundledFile` | Bundled (image-baked) | `/app/resources/` |
| `ListSessionFiles` | Session-uploaded | `$HOME` (`/home/session`) |
| `ReadSessionFile` | Session-uploaded | `$HOME` (`/home/session`) |

## Security model — distinct tools, distinct sandboxes

Each tool takes a `fileName` (no directory components allowed) and enforces three layers of defence inside the implementation:

1. **`Path.GetFileName(input)`** strips any directory parts from the model-supplied name. `"../../etc/passwd"` becomes `"passwd"`.
2. **`Path.GetFullPath(Combine(root, name))`** canonicalises the path.
3. **`fullPath.StartsWith(root + DirectorySeparatorChar)`** rejects anything that resolves outside the tool's root.

Failures return a controlled `"File '<input>' not found in <scope>."` rather than throwing or exposing the canonical path.

This is why the agent has four narrowly-scoped tools instead of a single `ReadFile(path)`:

- **Smaller per-tool attack surface.** Each tool has one purpose, one root, and no path-typed parameter. Even a buggy implementation can only leak its own directory.
- **Cross-boundary access is impossible by schema.** A prompt-injection attempt to make the bundled tool read a session path (or vice versa) does not even compile in the tool schema the model sees.
- **Read-only, non-recursive listing.** No write tools, no glob, no `..`.

## Companion

[`Using-Samples/SessionFilesClient`](../Using-Samples/SessionFilesClient/) — a thin chat REPL (same shape as [`SimpleAgent`](../Using-Samples/SimpleAgent/)) that points at the deployed Hosted-Files endpoint via `FoundryAgent` and lets you ask questions whose answers come from either file source.

## Live proof of the session-files contract

The end-to-end alpha-SDK round trip (client uploads via `AgentSessionFiles.UploadSessionFileAsync` → file arrives at `$HOME/<name>` inside the per-session container → agent's `ReadSessionFile` tool reads it → response quotes the verbatim contents) is exercised live by [`SessionFilesHostedAgentTests.UploadedFile_IsReadByHostedAgentAsync`](../../../../../tests/Foundry.Hosting.IntegrationTests/SessionFilesHostedAgentTests.cs) against the matching `session-files` scenario in the integration test container.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- An Azure AI Foundry project with a deployed model (e.g., `gpt-4o`)
- Azure CLI logged in (`az login`)

## Configuration

Copy the template and fill in your project endpoint:

```bash
cp .env.example .env
```

Edit `.env`:

```env
AZURE_AI_PROJECT_ENDPOINT=https://<your-account>.services.ai.azure.com/api/projects/<your-project>
ASPNETCORE_URLS=http://+:8088
ASPNETCORE_ENVIRONMENT=Development
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o
```

> `.env` is gitignored. The `.env.example` template is checked in as a reference.

## Running directly (contributors)

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-Files
AGENT_NAME=hosted-files dotnet run
```

The agent starts on `http://localhost:8088`.

## Try it from the SessionFilesClient REPL

### Bundled files (works against any deployment, including local)

```bash
cd ../Using-Samples/SessionFilesClient
$env:AGENT_ENDPOINT = "http://localhost:8088"
$env:AGENT_NAME = "hosted-files"
dotnet run

You> What is the total revenue in the contoso file?
Agent> The contoso file reports total revenue of "$1,482.6M".
```

The agent calls `ListBundledFiles`, sees `contoso_q1_2026_report.txt`, calls `ReadBundledFile("contoso_q1_2026_report.txt")` (which resolves under `/app/resources/`), and quotes the figure verbatim.

### Session files (against a deployed agent)

Upload a file to a specific session via `azd ai agent files upload` or via the alpha `AgentSessionFiles` SDK (see the integration test for the SDK call), then ask the agent about it. The agent's `ReadSessionFile` tool reads from `$HOME` and surfaces the content the same way.

## Running with Docker

This project uses `ProjectReference`, so use `Dockerfile.contributor` which takes a pre-published output:

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
docker build -f Dockerfile.contributor -t hosted-files .

export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
docker run --rm -p 8088:8088 \
  -e AGENT_NAME=hosted-files \
  -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN \
  --env-file .env \
  hosted-files
```

The bundled `resources/` folder is part of the published output and ships inside the image.

## NuGet package users

If consuming the Agent Framework as a NuGet package, use the standard `Dockerfile` instead of `Dockerfile.contributor` and switch the `ProjectReference` entries in `HostedFiles.csproj` to `PackageReference` (commented section in the csproj).

## Adding more bundled files

Drop additional text files into [`resources/`](./resources/). The csproj `<Content Include="resources\**\*" CopyToOutputDirectory="PreserveNewest" />` rule picks them up on the next `dotnet build` / `docker build`.

## Overrides

| Env var | Purpose | Default |
|---------|---------|---------|
| `BUNDLED_FILES_DIR` | Override the bundled-files root the tools read from. | `<process base dir>/resources` (`/app/resources/` in container) |
| `HOME` | The per-session sandbox volume root the session-files tools read from. Set by the Foundry platform; can be overridden for local testing. | `/home/session` |