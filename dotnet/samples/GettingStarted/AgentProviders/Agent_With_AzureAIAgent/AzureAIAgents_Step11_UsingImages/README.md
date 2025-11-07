# Using Images with AI Agents

This sample demonstrates how to use image multi-modality with an AI agent. It shows how to create a vision-enabled agent that can analyze and describe images using Azure OpenAI.

## What this sample demonstrates

- Creating a persistent AI agent with vision capabilities
- Sending both text and image content to an agent in a single message
- Using `UriContent` to Uri referenced images
- Processing multimodal input (text + image) with an AI agent

## Key features

- **Vision Agent**: Creates an agent specifically instructed to analyze images
- **Multimodal Input**: Combines text questions with image uri in a single message
- **Azure OpenAI Integration**: Uses AzureOpenAI LLM agents

## Prerequisites

Before running this sample, ensure you have:

1. An Azure OpenAI project set up
2. A compatible model deployment (e.g., gpt-4o)
3. Azure CLI installed and authenticated

## Environment Variables

Set the following environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" # Replace with your Azure OpenAI endpoint
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o" # Replace with your model deployment name (optional, defaults to gpt-4o)
```

## Run the sample

Navigate to the sample directory and run:

```powershell
cd Agent_Step11_UsingImages
dotnet run
```

## Expected behavior

The sample will:

1. Create a vision-enabled agent named "VisionAgent"
2. Send a message containing both text ("What do you see in this image?") and a Uri image of a green walk
3. The agent will analyze the image and provide a description
4. Clean up resources by deleting the thread and agent

