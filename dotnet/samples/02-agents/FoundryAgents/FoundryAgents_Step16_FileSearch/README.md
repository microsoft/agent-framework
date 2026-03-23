# Using File Search with AI Agents

This sample demonstrates how to use the file search tool with AI agents. The file search tool allows agents to search through uploaded files stored in vector stores to answer user questions.

## What this sample demonstrates

- Uploading files and creating vector stores
- Creating agents with file search capabilities
- Using HostedFileSearchTool (MEAI abstraction)
- Using native SDK file search tools (ResponseTool.CreateFileSearchTool)
- Handling file citation annotations
- Managing agent and resource lifecycle (creation and deletion)

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure Foundry service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)

**Note**: This demo uses `DefaultAzureCredential` for authentication. For local development, make sure you're logged in with `az login` and have access to the Azure Foundry resource. For more information, see the [Azure Identity documentation](https://learn.microsoft.com/dotnet/api/azure.identity.defaultazurecredential).

Set the following environment variables:

```powershell
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Azure Foundry resource endpoint
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/02-agents/FoundryAgents
dotnet run --project .\FoundryAgents_Step16_FileSearch
```

## Expected behavior

The sample will:

1. Create a temporary text file with employee directory information
2. Upload the file to Azure Foundry
3. Create a vector store with the uploaded file
4. Create an agent with file search capabilities using one of:
   - Option 1: Using HostedFileSearchTool (MEAI abstraction)
   - Option 2: Using native SDK file search tools
5. Run a query against the agent to search through the uploaded file
6. Display file citation annotations from responses
7. Clean up resources (agent, vector store, and uploaded file)
