# Host a workflow in a container

This sample hosts a pro-code workflow in ASP.NET Core and packages it as a non-root
Linux container. It routes an expense through two executors: normalize the expense
ID, then select standard review (amount <= 100) or manager review (amount > 100).
The rules are deterministic so you can verify the hosting setup without a model,
cloud account, credentials, or external business system.

Each HTTP request builds its own workflow and executors. Cancelling a request ends
event consumption; disposing its `StreamingRun` stops the underlying execution.
An executor failure produces an HTTP 500 response rather than a successful result.

## Run locally

Install the .NET SDK specified in `dotnet/global.json`. From the repository root:

```sh
dotnet run --project dotnet/samples/04-hosting/ContainerWorkflow -f net10.0 -- --urls http://localhost:8080
```

In another terminal:

```sh
curl http://localhost:8080/health
curl -H "Content-Type: application/json" -d '{"id":"EXP-001","amount":150}' http://localhost:8080/expenses
```

Expected response:

```json
{"id":"EXP-001","amount":150,"route":"manager_review"}
```

For PowerShell, use:

```powershell
Invoke-RestMethod http://localhost:8080/expenses -Method Post -ContentType application/json -Body '{"id":"EXP-001","amount":150}'
```

Amounts of 100 or less select `standard_review`. A missing/blank ID, an ID longer
than 128 characters, or a non-positive amount returns HTTP 400. Malformed JSON is
also rejected by ASP.NET Core.

## Build and run the container

With Docker running in Linux-container mode, run these commands from the repository
root. The build uses project references to compile this checkout of the framework.
The Dockerfile-specific ignore file limits the build context to .NET sources and
excludes local build output and common credential files.

```sh
docker build -f dotnet/samples/04-hosting/ContainerWorkflow/Dockerfile -t agent-framework-workflow .
docker run --rm --name agent-framework-workflow -p 127.0.0.1:8080:8080 agent-framework-workflow
```

Use the same requests above to verify the container. Stop it with Ctrl+C, or from
another terminal:

```sh
docker stop agent-framework-workflow
```

## Hosting boundaries

This is an in-process, request/response deployment example. It does not persist
workflow state across process restarts, execute payments, or provide a human
approval UI. The expense ID is returned for correlation; it is not an idempotency
key. Repeating a request executes a new workflow.

The endpoint is unauthenticated for local testing. Add application authentication
and authorization before exposing it to other users. No inbound credentials or
request bodies are deliberately logged by the sample.

For cloud-managed hosting, see [Foundry hosted agents](../FoundryHostedAgents).
For durable agents and external scheduling, see the
[Durable Agent Framework extension](https://github.com/microsoft/agent-framework-durable-extension).
