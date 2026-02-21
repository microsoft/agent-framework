# Structured Output with ChatClientAgent

This sample demonstrates how to configure ChatClientAgent to produce structured output in JSON format using various approaches.

## What this sample demonstrates

- **ResponseFormat approach**: Configuring agents with JSON schema response format via `ChatResponseFormat.ForJsonSchema<T>()` for inter-agent communication or when the type is not known at compile time
- **Generic RunAsync<T> method**: Using the generic `RunAsync<T>` method for structured output when the caller needs to work directly with typed objects
- **Structured output with Streaming**: Using `RunStreamingAsync` to stream responses while still obtaining structured output by assembling and deserializing the streamed content
- **StructuredOutput middleware**: Adding structured output support to agents that don't natively support it (like A2A agents or models without structured output capability) by transforming text output into structured data using a chat client

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)
- User has the `Cognitive Services OpenAI Contributor` role for the Azure OpenAI resource

**Note**: This sample uses Azure OpenAI models. For more information, see [how to deploy Azure OpenAI models with Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/deploy-models-openai).

**Note**: This demo uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource and have the `Cognitive Services OpenAI Contributor` role. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Environment Variables

Set the following environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" # Replace with your Azure OpenAI resource endpoint
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Run the sample

Navigate to the sample directory and run:

```powershell
cd dotnet/samples/02-agents/Agents/Agent_Step02_StructuredOutput
dotnet run
```

## Expected behavior

The sample will demonstrate four different approaches to structured output:

1. **Structured Output with ResponseFormat**: Creates an agent with `ResponseFormat` set to `ForJsonSchema<CityInfo>()`, invokes it with unstructured input, and accesses the structured output via the `Text` property
2. **Structured Output with RunAsync<T>**: Creates an agent and uses the generic `RunAsync<CityInfo>()` method to get a typed `AgentResponse<CityInfo>` with the result accessible via the `Result` property
3. **Structured Output with RunStreamingAsync**: Creates an agent with JSON schema response format, streams the response using `RunStreamingAsync`, assembles the updates using `ToAgentResponseAsync()`, and deserializes the JSON text into a typed object
4. **Structured Output with StructuredOutput Middleware**: Uses the `UseStructuredOutput` method on `AIAgentBuilder` to add structured output support to agents that don't natively support it

Each approach will output information about the capital of France (Paris) in a structured format.
