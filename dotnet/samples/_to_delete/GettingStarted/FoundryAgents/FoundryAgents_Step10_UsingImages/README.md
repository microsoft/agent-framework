# Using Images with AI Agents

This sample demonstrates how to use image multi-modality with an AI agent. It shows how to create a vision-enabled agent that can analyze and describe images using Azure Foundry Agents.

## What this sample demonstrates

- Creating a vision-enabled AI agent with image analysis capabilities
- Sending both text and image content to an agent in a single message
- Using `UriContent` for URI-referenced images
- Processing multimodal input (text + image) with an AI agent
- Managing agent lifecycle (creation and deletion)

## Key features

- **Vision Agent**: Creates an agent specifically instructed to analyze images
- **Multimodal Input**: Combines text questions with image URI in a single message
- **Azure Foundry Agents Integration**: Uses Azure Foundry Agents with vision capabilities

## Prerequisites

Before running this sample, ensure you have:

1. An Azure OpenAI project set up
2. A compatible model deployment (e.g., gpt-4o)
3. Azure CLI installed and authenticated

## Environment Variables

Set the following environment variables:

```powershell
$env:AZURE_FOUNDRY_PROJECT_ENDPOINT="https://your-resource.openai.azure.com/" # Replace with your Azure Foundry Project endpoint
$env:AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME="gpt-4o" # Replace with your model deployment name (optional, defaults to gpt-4o)
```

## Run the sample

Navigate to the FoundryAgents sample directory and run:

```powershell
cd dotnet/samples/GettingStarted/FoundryAgents
dotnet run --project .\FoundryAgents_Step10_UsingImages
```

## Expected behavior

The sample will:

1. Create a vision-enabled agent named "VisionAgent"
2. Send a message containing both text ("What do you see in this image?") and a URI-referenced image of a green walkway (nature boardwalk)
3. The agent will analyze the image and provide a description
4. Clean up resources by deleting the agent

