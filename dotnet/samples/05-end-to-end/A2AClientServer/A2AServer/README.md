# A2A server

This server hosts a policy agent and exposes it through the A2A JSON-RPC and
HTTP+JSON protocol bindings.

## Run the server

Authenticate with Azure CLI and configure your Microsoft Foundry project:

```powershell
az login
$env:FOUNDRY_PROJECT_ENDPOINT="<your-project-endpoint>"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
```

Start the server:

```powershell
cd dotnet\samples\05-end-to-end\A2AClientServer\A2AServer
dotnet run
```

The server must remain running while you use the client, the HTTP requests, or
the A2A Inspector. By default, it listens at `http://localhost:5000`.

`ASPNETCORE_URLS` controls the address the server listens on, and
`A2A_AGENT_URL` controls the public URL advertised in the agent card. Both
default to `http://localhost:5000`. Set them together when the server should
run at a different address.

## Test with the HTTP file

Open `A2AServer.http` in an editor that supports HTTP files, such as Visual
Studio or Visual Studio Code with an HTTP client extension, and run either request:

1. `Query the policy agent card` retrieves the discovery document.
2. `Send a message to the policy agent` invokes the agent through JSON-RPC.

Start the server before running these requests. If the server uses a different
address, update the `@host` variable at the top of `A2AServer.http`.

## Inspect with A2A Inspector

Follow the [A2A Inspector setup instructions](https://github.com/a2aproject/a2a-inspector),
start the Inspector, and connect it to `http://localhost:5000`.

The Inspector discovers `/.well-known/agent-card.json`, displays the policy
agent card, and lets you send messages to the running server.
