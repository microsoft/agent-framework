# Microsoft.Agents.AI.AGUI has moved

> [!IMPORTANT]
> The in-tree `Microsoft.Agents.AI.AGUI` package has been **removed**. Its AG-UI protocol
> abstractions now live in the official **AG-UI C# SDK** (`AGUI.*` packages) published on NuGet.org
> by the AG-UI team. This folder is intentionally kept only to host this migration note.

## Why it moved

Microsoft Agent Framework used to carry its own copy of the AG-UI protocol (events, messages, tools,
interrupts, state, multimodal, SSE and protobuf transports). That protocol is now maintained once, in
the AG-UI C# SDK, and stays wire compatible with the TypeScript and Python SDKs. MAF no longer tracks
protocol changes in a second implementation and keeps only the ASP.NET hosting glue that is genuinely
framework specific.

The programming model is unchanged: the SDK is built on `Microsoft.Extensions.AI`, so `IChatClient`
remains the single integration point on both the client and the server.

## Where things went

| You used (old) | Use this now (NuGet) |
| --- | --- |
| `Microsoft.Agents.AI.AGUI` (client) | [`AGUI.Client`](https://www.nuget.org/packages/AGUI.Client) |
| `Microsoft.Agents.AI.AGUI` (server adapters) | [`AGUI.Server`](https://www.nuget.org/packages/AGUI.Server) |
| `Microsoft.Agents.AI.AGUI` (events / messages / tools) | [`AGUI.Abstractions`](https://www.nuget.org/packages/AGUI.Abstractions) |
| protobuf transport (opt in) | [`AGUI.Protobuf`](https://www.nuget.org/packages/AGUI.Protobuf) |
| wire formatting helpers | [`AGUI.Formatting`](https://www.nuget.org/packages/AGUI.Formatting) |

The ASP.NET hosting integration stays in this repository as
[`Microsoft.Agents.AI.Hosting.AGUI.AspNetCore`](../Microsoft.Agents.AI.Hosting.AGUI.AspNetCore),
now layered over the `AGUI.Server` primitives.

Source of the SDK packages: [ag-ui-protocol/ag-ui](https://github.com/ag-ui-protocol/ag-ui)
(see [PR #1963](https://github.com/ag-ui-protocol/ag-ui/pull/1963)).

## Migration guide

### 1. Package references

Drop the reference to `Microsoft.Agents.AI.AGUI` and add the `AGUI.*` packages you actually use
(`AGUI.Client` for clients, `AGUI.Server` plus `AGUI.Abstractions` for server and hosting, plus
`AGUI.Protobuf` if you opt into the protobuf transport).

### 2. Hosting entry points renamed

The two hosting methods were renamed to match the sibling `AddA2AServer` convention. The old names
are gone.

```csharp
// Before
builder.Services.AddAGUI();
app.MapAGUI("/", agent);

// After
builder.Services.AddAGUIServer();
app.MapAGUIServer("/", agent);
```

### 3. Namespaces

The single `Microsoft.Agents.AI.AGUI` namespace splits along the SDK package boundaries:
`AGUI.Client`, `AGUI.Server`, and `AGUI.Abstractions`.

### 4. `AGUIChatClient` construction

The positional constructor becomes options based.

```csharp
// Before
using Microsoft.Agents.AI.AGUI;
var chatClient = new AGUIChatClient(
    httpClient,
    serverUrl,
    jsonSerializerOptions: AGUIClientSerializerContext.Default.Options);

// After
using AGUI.Client;
var chatClient = new AGUIChatClient(new(httpClient, serverUrl)
{
    JsonSerializerOptions = AGUIClientSerializerContext.Default.Options,
});
```

### 5. Recovering the originating AG-UI input on the server

Read it back from `ChatOptions` via the SDK extension.

```csharp
using AGUI.Abstractions;
using AGUI.Server;

if (!chatOptions.TryGetRunAgentInput(out RunAgentInput? agentInput))
{
    // not an AG-UI-originated request
}
```

## Samples

Working end to end samples that use the external packages live under:

- [`samples/02-agents/AGUI`](../../samples/02-agents/AGUI)
- [`samples/05-end-to-end/AGUIClientServer`](../../samples/05-end-to-end/AGUIClientServer)
- [`samples/05-end-to-end/AGUIWebChat`](../../samples/05-end-to-end/AGUIWebChat)
