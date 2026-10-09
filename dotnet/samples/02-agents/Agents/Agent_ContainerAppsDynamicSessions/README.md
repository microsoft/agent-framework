# Azure Container Apps Dynamic Sessions

This sample gives an Agent Framework agent a function tool that runs Python in an
Azure Container Apps code-interpreter session. It uses the existing HTTP and Azure
identity libraries to call the [code execution REST API](https://learn.microsoft.com/rest/api/data-plane/containerapps/code-execution/execute).
Generated code runs in the cloud session, not on the machine running this sample.

## Setup

Use .NET 10 and an existing Microsoft Foundry model deployment. Create a Python
code-interpreter session pool using the [Dynamic Sessions setup guide](https://learn.microsoft.com/azure/container-apps/sessions-usage).
The signed-in identity needs `Azure ContainerApps Session Executor` on the pool
and permission to invoke the Foundry model. Sign in with `az login`.

Retrieve the pool management endpoint from
`az containerapp sessionpool show --name <pool> --resource-group <group> --query properties.poolManagementEndpoint --output tsv`.
Then configure and run:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT = "<project-endpoint>"
$env:FOUNDRY_MODEL = "<model-deployment>"
$env:POOL_MANAGEMENT_ENDPOINT = "<pool-management-endpoint>"
dotnet run
```

The agent asks the tool to calculate an order total with tax. The tool returns
the execution status and result, including standard output and errors. HTTP
failures are surfaced to the agent's function invocation pipeline. Each execution
is limited to 30 seconds with a bounded output stream; the HTTP client allows
additional time for transport and pool startup.

## Session ownership and lifecycle

The application generates a new session identifier for each run and reuses it
for that run's tool calls, allowing Python state to persist between calls. The
model supplies only code, not the endpoint or session identifier. For a multi-user
host, bind a separate tool/session identifier to each authorized conversation.
Do not share a session across unrelated users.

Use only a trusted pool management endpoint. Configure the pool's network access
for your workload and do not pass application credentials or confidential data
into generated code. This example uses interactive developer authentication;
deployed applications should use an identity configured for their host.

The sample does not provision or delete Azure resources. The pool's configured
cooldown manages idle session cleanup. Model and pool usage incur costs.
