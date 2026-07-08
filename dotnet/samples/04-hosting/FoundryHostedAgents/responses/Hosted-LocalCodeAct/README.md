# Hosted-LocalCodeAct

A hosted agent that uses [`Microsoft.Agents.AI.LocalCodeAct`](../../../../../src/Microsoft.Agents.AI.LocalCodeAct/README.md)
to give the model a single `execute_code` tool. Two sandbox-only host tools,
`compute` and `fetch_data`, are registered on `LocalCodeActProvider` and are
reachable from inside generated Python via `await call_tool(...)` — never as
direct LLM tool calls.

This mirrors the Python
[`foundry_hosted_agent.py`](https://github.com/microsoft/agent-framework/blob/main/python/packages/local_codeact/samples/foundry_hosted_agent.py)
sample for the `agent-framework-local-codeact` package.

> **⚠️ Security:** LocalCodeAct executes LLM-generated Python in the agent
> process. The package is not a sandbox — it relies on the Foundry hosted-agent
> container (or another externally sandboxed environment) for process,
> filesystem, and network isolation. Do not run this outside of a sandbox.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/download/dotnet/10.0)
- Python 3 available on `PATH` (used by `LocalCodeActProvider` to execute the
  embedded runner and validator). Override with the `LOCAL_CODEACT_PYTHON`
  environment variable if you need a specific interpreter path.
- A Foundry project with a deployed model (e.g., `gpt-4o`)
- Azure CLI logged in (`az login`)

## Configuration

Copy the template and fill in your project endpoint:

```bash
cp .env.example .env
```

Edit `.env` and set your Foundry project endpoint:

```env
FOUNDRY_PROJECT_ENDPOINT=https://<your-account>.services.ai.azure.com/api/projects/<your-project>
ASPNETCORE_URLS=http://+:8088
ASPNETCORE_ENVIRONMENT=Development
FOUNDRY_MODEL=gpt-4o
LOCAL_CODEACT_PYTHON=python3
```

> **Note:** `.env` is gitignored. The `.env.example` template is checked in as a reference.

## Running directly (contributors)

This project uses `ProjectReference` to build against the local Agent Framework
source, including the `Microsoft.Agents.AI.LocalCodeAct` package.

```bash
cd dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-LocalCodeAct
AGENT_NAME=hosted-local-codeact dotnet run
```

The agent will start on `http://localhost:8088`.

### Test it

Using the Azure Developer CLI:

```bash
azd ai agent invoke --local "Fetch all users, find the admins, multiply 7 by 6, and print the users, admins, and the multiplication result. Use execute_code with await call_tool(...)."
```

Or with curl:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Fetch all users, find the admins, multiply 7 by 6, and print the users, admins, and the multiplication result. Use execute_code with await call_tool(...).", "model": "hosted-local-codeact"}'
```

## Running with Docker

Since this project uses `ProjectReference`, use `Dockerfile.contributor` which
takes a pre-published output. The image installs Python 3 so the embedded
runner and validator scripts can execute.

### 1. Publish for the container runtime (Linux Alpine)

```bash
dotnet publish -c Debug -f net10.0 -r linux-musl-x64 --self-contained false -o out
```

### 2. Build the Docker image

```bash
docker build -f Dockerfile.contributor -t hosted-local-codeact .
```

### 3. Run the container

Generate a bearer token on your host and pass it to the container:

```bash
# Generate token (expires in ~1 hour)
export AZURE_BEARER_TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

# Run with token
docker run --rm -p 8088:8088 \
  -e AGENT_NAME=hosted-local-codeact \
  -e AZURE_BEARER_TOKEN=$AZURE_BEARER_TOKEN \
  --env-file .env \
  hosted-local-codeact
```

### 4. Test it

```bash
azd ai agent invoke --local "Fetch all users and print the admins."
```

## How CodeAct works here

`LocalCodeActProvider` is registered as an `AIContextProvider`. On every run it
injects:

- A single `execute_code` tool that the model can call with a Python snippet.
- CodeAct instructions that teach the model to use `await call_tool(...)` for
  the provider-owned host tools, rather than asking for direct tool calls.

The provider-owned host tools in this sample:

| Tool | Description |
|------|-------------|
| `compute(operation, a, b)` | Math operation: `add`, `subtract`, `multiply`, `divide`. |
| `fetch_data(table)` | Returns rows from a simulated `users` or `products` table. |

`execute_code` runs the generated Python in a separate Python process governed
by `ProcessExecutionLimits` (5 second timeout in this sample) and the
default-on AST allow-list validator that rejects disallowed imports, builtins,
and dynamic-eval constructs before execution.

## Deploying to Foundry (azd spec)

This sample includes an `azd` manifest (`agent.manifest.yaml`) and hosted agent
spec (`agent.yaml`) for deployment to Foundry.

Initialize an `azd` project from this sample's manifest:

```bash
mkdir hosted-local-codeact && cd hosted-local-codeact
azd ai agent init -m https://github.com/microsoft/agent-framework/blob/main/dotnet/samples/04-hosting/FoundryHostedAgents/responses/Hosted-LocalCodeAct/agent.manifest.yaml
```

Then deploy:

```bash
azd deploy
```

## NuGet package users

If you are consuming the Agent Framework as a NuGet package (not building from
source), use the standard `Dockerfile` instead of `Dockerfile.contributor`. See
the commented section in `HostedLocalCodeAct.csproj` for the `PackageReference`
alternative.
