# Using Images with AI Agents

This sample demonstrates how to use image multi-modality with an AI agent. It shows how to create a vision-enabled agent that can analyze and describe images using Microsoft Foundry with `AIProjectClient`.

## What this sample demonstrates

- Creating a persistent AI agent with vision capabilities
- Sending both text and image content to an agent in a single message
- Using `UriContent` to Uri referenced images
- Processing multimodal input (text + image) with an AI agent

## Key features

- **Vision Agent**: Creates an agent specifically instructed to analyze images
- **Multimodal Input**: Combines text questions with image uri in a single message
- **Microsoft Foundry Integration**: Uses `AIProjectClient` to create a Foundry-backed agent

## Prerequisites

Before running this sample, ensure you have:

1. A Microsoft Foundry project set up
2. A compatible model deployment (e.g., gpt-5.4-mini)
3. Azure CLI installed and authenticated

## Environment Variables

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://<your-project>.services.ai.azure.com/api/projects/<your-project>" # Replace with your Foundry project endpoint
$env:FOUNDRY_MODEL="gpt-5.4-mini" # Replace with your model name (optional, defaults to gpt-5.4-mini)
```

## Run the sample

Navigate to the sample directory and run:

```powershell
cd Agent_Step08_UsingImages
dotnet run
```

## Expected behavior

The sample will:

1. Create a vision-enabled agent named "VisionAgent"
2. Send a message containing both text ("What do you see in this image?") and a Uri image of a green walk
3. The agent will analyze the image and provide a description
4. Clean up resources by deleting the thread and agent
