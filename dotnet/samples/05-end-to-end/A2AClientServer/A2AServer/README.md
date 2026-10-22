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

## Agent card and server settings

Publishing an agent card only provides discovery information; it does not
configure the separately registered A2A server. This sample derives the server
settings from the same card that it publishes:

```csharp
builder.AddA2AServer(policyAgent, options =>
{
    options.ServerOptions = new A2AServerOptions
    {
        SupportsStreaming = policyAgentCard.Capabilities.Streaming == true,
        SupportedInputModes = policyAgentCard.DefaultInputModes
            .Concat(policyAgentCard.Skills.SelectMany(skill => skill.InputModes ?? []))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray(),
    };
});
```

The input modes include both the card defaults and any skill-specific modes,
with case-insensitive duplicates removed. The policy card disables streaming
and accepts `text/plain`, so both protocol bindings reject streaming requests
and message parts that declare other media types, such as `image/png`, before
invoking the agent. Parts without a declared media type are not rejected by
this media-type check.

When `ServerOptions` is not configured, the underlying SDK defaults still
apply: streaming is enabled, and input media types are not restricted.

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
