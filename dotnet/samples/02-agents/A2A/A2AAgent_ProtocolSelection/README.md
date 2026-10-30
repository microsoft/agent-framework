# A2A Agent Protocol Selection

This sample demonstrates how to select the A2A protocol binding when creating an `AIAgent` from an A2A agent card.

A2A agents can expose multiple interfaces with different protocol bindings (e.g., HTTP+JSON, JSON-RPC, gRPC). By default, `AsAIAgent()` selects the first HTTP+JSON or JSON-RPC interface listed in the agent card. This sample shows how to use `A2AClientOptions.PreferredBindings` to explicitly control which protocol binding is used.

The sample uses only the selected binding; it does not fall back to another protocol.

The sample:

- Connects to an A2A agent server specified in the `A2A_AGENT_HOST` environment variable
- Selects the binding using `A2A_PROTOCOL_BINDING`, defaulting to HTTP+JSON
- Explicitly registers the gRPC client factory when gRPC is selected
- Creates an `AIAgent` from the resolved agent card using the specified binding
- Sends a message to the agent and displays the response

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10.0 SDK or later
- An A2A agent server running and accessible via HTTP, with support for the selected binding

**Note**: These samples need to be run against a valid A2A server. If no A2A server is available, they can be run against the echo-agent that can be spun up locally by following the guidelines at: https://github.com/a2aproject/a2a-dotnet/blob/main/samples/AgentServer/README.md

The linked echo-agent does not expose gRPC. To select `GRPC`, use a server whose agent card lists a `GRPC` interface.

Set the following environment variable:

```powershell
$env:A2A_AGENT_HOST="http://localhost:5000"  # Replace with your A2A agent server host
```

Optionally select a binding:

```powershell
$env:A2A_PROTOCOL_BINDING="GRPC"  # Or "HTTP+JSON" (default) or "JSONRPC"
dotnet run
```

## gRPC client setup

The sample already references `Microsoft.Agents.AI.A2A` and the SDK's `A2A.Grpc` package.
The existing `A2AAgent` works with `A2AGrpcClient`; no additional framework package is needed.
The base `Microsoft.Agents.AI.A2A` package does not bring in gRPC dependencies.

To add the same support to your own application:

```powershell
dotnet add package Microsoft.Agents.AI.A2A --prerelease
dotnet add package A2A.Grpc --prerelease
```

For agent-card discovery, explicitly register the SDK's gRPC binding once during application startup:

```csharp
using A2A;
using A2A.Grpc;
using Microsoft.Agents.AI;

A2AGrpcClientRegistration.Register();

var resolver = new A2ACardResolver(new Uri("https://agent.example.com/"));

AIAgent agent = await resolver.GetAIAgentAsync(
    options: new A2AClientOptions
    {
        PreferredBindings = [ProtocolBindingNames.Grpc]
    });

using var clientLifetime = agent.GetService<IA2AClient>() as IDisposable;

Console.WriteLine(await agent.RunAsync("Hello over gRPC!"));
```

The agent card must list a `GRPC` interface. Discovery fetches the card over HTTP,
then the client uses the gRPC endpoint listed in the card.

If you already know the gRPC endpoint, create the client directly. No registration is needed:

```csharp
using var client = new A2AGrpcClient(new Uri("https://agent.example.com:5001"));

AIAgent agent = client.AsAIAgent(name: "Remote agent");

Console.WriteLine(await agent.RunAsync("Hello!"));
```

Keep the client alive while using the agent and dispose it when finished; `A2AAgent` does not do this
for you. Use `using var client` for a direct connection, or the `clientLifetime` pattern shown above
for discovery.
