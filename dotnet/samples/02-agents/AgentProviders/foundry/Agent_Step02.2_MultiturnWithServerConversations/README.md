# Multi-turn Conversation with Server-Side Conversations

This sample demonstrates how to use server-side conversations with a `FoundryAgent`. Server-side conversations persist on the Foundry service and are visible in the Foundry Project UI, making them ideal when you need conversation history to be stored and accessible server-side.

## What this sample demonstrates

- Creating a `FoundryAgent` with instructions
- Using `CreateConversationSessionAsync` to create a server-side `ProjectConversation`
- Multi-turn conversations with both text and streaming output
- Server-side conversation persistence visible in the Foundry Project UI

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Microsoft Foundry service endpoint and deployment configured
- An authenticated Azure identity (for example, sign in with `az login`)

**Note**: This sample uses `DefaultAzureCredential`. `az login` is the easiest local development path, but Visual Studio, VS Code, and managed identity credentials also work when available.

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project"
$env:FOUNDRY_MODEL="gpt-5.4-mini"
```

## Run the sample

Navigate to the Foundry sample directory and run:

```powershell
cd dotnet/samples/02-agents/AgentProviders/foundry
dotnet run --project .\Agent_Step02.2_MultiturnWithServerConversations
```

