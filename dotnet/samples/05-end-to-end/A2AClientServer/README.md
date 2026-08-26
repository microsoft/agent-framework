# A2A policy agent client and server

This sample demonstrates a minimal end-to-end A2A flow:

1. `A2AServer` hosts a policy agent and publishes its agent card.
2. `A2AClient` discovers the policy agent and sends it messages over A2A.

## Prerequisites

- .NET 10 SDK
- A Microsoft Foundry project with a deployed model
- Azure CLI authentication (`az login`)

## Run the sample

Open two terminals from this directory.

In the first terminal, start the policy agent:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="<your-project-endpoint>"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
cd A2AServer
dotnet run
```

In the second terminal, start the client:

```powershell
cd A2AClient
dotnet run
```

Then ask:

```text
What is the policy for short shipments?
```

The server listens on `http://localhost:5000` by default. `A2AServer/A2AServer.http`
contains requests for inspecting the agent card and calling the agent directly.
The server must be running before using either the HTTP file or the
[A2A Inspector](https://github.com/a2aproject/a2a-inspector). See the server and
client READMEs for detailed instructions.

## Optional configuration

`FOUNDRY_MODEL` is optional and defaults to `gpt-5.4-mini`. The server creates the
policy agent with the Microsoft Foundry Responses API.

`A2A_AGENT_URL` optionally sets the public server URL advertised in the agent
card and defaults to `http://localhost:5000`.
