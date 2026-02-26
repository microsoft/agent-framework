# Using Computer Use Tool with AI Agents

This sample demonstrates how to use the computer use tool with AI agents. The computer use tool allows agents to interact with a computer environment by viewing the screen, controlling the mouse and keyboard, and performing various actions to help complete tasks.

> [!NOTE]
> **Azure Agents API vs. vanilla OpenAI Responses API behavior:**
> The Azure Agents API rejects requests that include `previous_response_id` alongside
> `computer_call_output` items — unlike the vanilla OpenAI Responses API, which accepts them.
> This sample works around the limitation by creating a **fresh session for each follow-up call**
> (so no `previous_response_id` is carried over) and re-sending all prior response output items
> (reasoning, computer_call, etc.) as input items to preserve full conversation context.
> Additionally, the sample uses the **current** `CallId` from each computer call response
> (not the initial one) and clears the `ContinuationToken` after polling completes to prevent
> stale tokens from affecting subsequent requests.

## What this sample demonstrates

- Creating agents with computer use capabilities
- Using HostedComputerTool (MEAI abstraction)
- Using native SDK computer use tools (ResponseTool.CreateComputerTool)
- Extracting computer action information from agent responses
- Handling computer tool results (text output and screenshots)
- Managing agent lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="computer-use-preview"  # Optional, defaults to computer-use-preview
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/02-agents/FoundryAgents
dotnet run --project .\FoundryAgents_Step15_ComputerUse
```

## Expected behavior

The sample will:

1. Create two agents with computer use capabilities:
   - Option 1: Using HostedComputerTool (MEAI abstraction)
   - Option 2: Using native SDK computer use tools
2. Run the agent with a task: "I need you to help me search for 'OpenAI news'. Please type 'OpenAI news' and submit the search. Once you see search results, the task is complete."
3. The agent will use the computer use tool to:
   - Interpret the screenshots
   - Issue action requests based on the task
   - Analyze the search results for "OpenAI news" from the screenshots.
4. Extract and display the computer actions performed
5. Display the results from the computer tool execution
6. Display the final response from the agent
7. Clean up resources by deleting both agents
