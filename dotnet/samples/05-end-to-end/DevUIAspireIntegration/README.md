# DevUI Integration Sample

This sample demonstrates how to use the **Aspire.Hosting.AgentFramework.DevUI** library to test and debug multiple AI agents through a unified DevUI web interface, orchestrated by an Aspire AppHost.

The solution contains two agent services:

- **WriterAgent** — a simple agent that writes short stories (≤ 300 words) about a given topic.
- **EditorAgent** — an agent that edits stories for grammar and style, selects a title, and formats the result for publishing. It also demonstrates tool use via `AIFunctionFactory`.

## Prerequisites

- [.NET 10 SDK](https://dotnet.microsoft.com/en-us/download/dotnet/10.0)
- [Aspire CLI](https://learn.microsoft.com/dotnet/aspire/fundamentals/setup-tooling)
- An Azure subscription with access to [Azure AI Foundry](https://learn.microsoft.com/azure/ai-studio/)
- Azure CLI authenticated (`az login`)

## Azure AI Foundry configuration

The sample requires an Azure AI Foundry resource with a deployed `gpt-4.1` model. You have two options:

### Option 1: Connect to an existing Foundry resource

Fill in the parameters in `DevUIIntegration.AppHost/appsettings.json`:

```json
{
    "Azure": {
        "TenantId": "<your-tenant-id>",
        "SubscriptionId": "<your-subscription-id>",
        "AllowResourceGroupCreation": true,
        "ResourceGroup": "<your-resource-group>",
        "Location": "<your-azure-region>",
        "CredentialSource": "AzureCli"
    },
    "Parameters": {
        "existingFoundryName": "<your-foundry-resource-name>",
        "existingFoundryResourceGroup": "<resource-group-containing-your-foundry>"
    }
}
```

The AppHost calls `foundry.AsExisting(...)` with these parameters, so Aspire connects to the existing resource instead of provisioning a new one.

### Option 2: Let Aspire provision a new Foundry resource

Remove or comment out the `AsExisting` block in `DevUIIntegration.AppHost/Program.cs`:

```csharp
// Comment the following lines to create a new Foundry instance
// _ = builder.AddParameterFromConfiguration("tenant", "Azure:TenantId");
// var existingFoundryName = builder.AddParameter("existingFoundryName") ...
// foundry.AsExisting(existingFoundryName, existingFoundryResourceGroup);
```

Aspire will provision a new Azure AI Foundry resource on startup. The DevUI resource uses `.WaitFor(foundry)` transitively through the agent services, so the frontend won't become available until provisioning completes. This can take several minutes on first run.

You still need to fill in the `Azure` section of `appsettings.json` (subscription, location, etc.) so Aspire knows where to create the resource.

## Agent name matching with `WithAgentService`

When connecting agent services to DevUI in the AppHost, you must pass the correct agent name via the `agents:` parameter. **This name must match the name used in `AddAIAgent(...)` inside each agent service's `Program.cs` — not the Aspire resource name.**

For example, the WriterAgent Aspire resource is named `"writer-agent"`, but the agent is registered as `"writer"`:

```csharp
// WriterAgent/Program.cs
builder.AddAIAgent("writer", "You write short stories ...");
//                  ^^^^^^^^ this is the agent name
```

```csharp
// EditorAgent/Program.cs
builder.AddAIAgent("editor", (sp, key) => { ... });
//                  ^^^^^^^^ this is the agent name
```

The AppHost must use these exact names:

```csharp
// DevUIIntegration.AppHost/Program.cs
builder.AddDevUI("devui")
    .WithAgentService(writerAgent, agents: [new("writer")])   // ✅ matches AddAIAgent("writer", ...)
    .WithAgentService(editorAgent, agents: [new("editor")])   // ✅ matches AddAIAgent("editor", ...)
    .WaitFor(writerAgent)
    .WaitFor(editorAgent);
```

Using the wrong name (e.g., `new("writer-agent")` instead of `new("writer")`) will cause the aggregator to send an entity ID the backend doesn't recognize, resulting in 404 errors when interacting with the agent.

If you omit the `agents:` parameter entirely, the aggregator defaults to a single agent named after the Aspire resource (e.g., `"writer-agent"`). Since agent services don't expose a `/v1/entities` discovery endpoint, **the Aspire resource name must exactly match the agent name registered via `AddAIAgent(...)` in the service's `Program.cs`**.

## Running the sample

```bash
cd dotnet/samples/05-end-to-end/DevUIAspireIntegration
aspire run
```

Once all services are running, open the **DevUI** URL shown in the Aspire dashboard. You should see both the writer and editor agents listed — select one and start a conversation.
