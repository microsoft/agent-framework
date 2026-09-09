# A2A client

This console client discovers and invokes the policy agent using the A2A protocol.

## Run the sample

Start the server in a separate terminal:

```powershell
az login
$env:FOUNDRY_PROJECT_ENDPOINT="<your-project-endpoint>"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
cd dotnet\samples\05-end-to-end\A2AClientServer\A2AServer
dotnet run
```

Keep the server running, then start the client:

```powershell
cd dotnet\samples\05-end-to-end\A2AClientServer\A2AClient
dotnet run
```

Ask a question such as `What is the policy for short shipments?`.

The client connects to `http://localhost:5000/` by default. To use another
endpoint, restart the server with its listening and advertised URLs set:

```powershell
$env:ASPNETCORE_URLS="http://localhost:6000"
$env:A2A_AGENT_URL="http://localhost:6000/"
dotnet run
```

Then set the discovery URL before starting the client:

```powershell
$env:A2A_AGENT_URL="http://localhost:6000/"
dotnet run
```

## Test the server with the HTTP file

With the server running, open `..\A2AServer\A2AServer.http` in an editor that
supports HTTP files, such as Visual Studio or Visual Studio Code with an HTTP
client extension. Run the first request to retrieve the agent card, or the
second request to invoke the policy agent directly.

The file targets `http://localhost:5000` by default. Update its `@host` variable
if the server listens at another address.

## Inspect the server with A2A Inspector

Follow the [A2A Inspector setup instructions](https://github.com/a2aproject/a2a-inspector)
and connect it to the running server at `http://localhost:5000`.

The Inspector provides another A2A client for viewing the agent card and sending
messages without running this console client.
