# Declarative OpenAI Agents

This sample demonstrates how to use the `OpenAIPromptAgentFactory` to create AI agents from YAML definitions.

## Overview

Unlike the `ChatClientPromptAgentFactory` which requires you to create an `IChatClient` upfront, the `OpenAIPromptAgentFactory` can create the chat client based on the model definition in the YAML file. This is useful when:

- You want the model to be defined declaratively in the YAML file
- You need to support multiple models without changing code
- You want to use Azure OpenAI endpoints with token-based authentication

## Prerequisites

- .NET 10.0 SDK
- Azure OpenAI endpoint access
- Azure CLI installed and authenticated (`az login`)

## Configuration

Set the following environment variable:

```bash
# Required: Azure OpenAI endpoint URL
set AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
```

## Running the Sample

```bash
dotnet run -- <yaml-file-path> <prompt>
```

### Example

```bash
dotnet run -- agent.yaml "What is the weather in Seattle?"
```

## Sample YAML Agent Definition

Create a file named `agent.yaml` with the following content:

```yaml
name: WeatherAgent
description: An agent that can provide weather information
model:
  api: chat
  configuration:
    azure_deployment: gpt-4o-mini
instructions: |
  You are a helpful assistant that provides weather information.
  Use the GetWeather function when asked about weather conditions.
```

## Key Differences from ChatClient Sample

| Feature | ChatClient Sample | OpenAI Sample |
|---------|------------------|---------------|
| Chat client creation | Manual (in code) | Automatic (from YAML model definition) |
| Model selection | Code-specified | YAML-specified |
| Factory class | `ChatClientPromptAgentFactory` | `OpenAIPromptAgentFactory` |
| Authentication | Passed to `AzureOpenAIClient` | Passed to factory constructor |
