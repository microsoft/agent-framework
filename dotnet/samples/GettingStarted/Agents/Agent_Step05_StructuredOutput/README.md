# Structured Output Sample

This sample demonstrates how to configure ChatClientAgent to produce structured output.

## Overview

Structured output is a valuable feature of AI agents that allows you to force an agent to produce output in a required format with specific fields. This makes it easy to turn unstructured data into structured data using a general-purpose language model.

The sample shows two approaches:
1. Using the generic `RunAsync<T>` method to request structured output at invocation time
2. Using `ChatOptions.ResponseFormat` to configure structured output at agent construction time

## Model Compatibility

**Important**: Not all models support structured output with JSON schema.

### Models with Full JSON Schema Support

The following models have native support for structured output with JSON schema:
- OpenAI GPT-4o and GPT-4o-mini (2024-08-06 and later)
- Azure OpenAI GPT-4o and GPT-4o-mini (2024-08-06 and later)
- OpenAI GPT-4 Turbo (certain versions)

### Models with Limited or No JSON Schema Support

Some models do not support JSON schema-based structured output, including:
- **Ollama models** (e.g., gpt-oss, llama3, phi3, etc.) - These models do not support native JSON schema validation
- Older OpenAI models
- Some other open-source models

## Troubleshooting

### Empty or Missing Responses

If you experience empty responses when using structured output, your model may not support JSON schema. You have two options:

#### Option 1: Use a Model with JSON Schema Support

Switch to a model that supports JSON schema (see list above).

#### Option 2: Disable JSON Schema Format

When calling `RunAsync<T>`, set `useJsonSchemaResponseFormat` to `false`:

```csharp
AgentRunResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>(
    "Please provide information about John Smith, who is a 35-year-old software engineer.",
    useJsonSchemaResponseFormat: false);
```

This will use JSON mode without schema validation. The model will attempt to produce JSON output, but there's no guarantee it will match your exact schema. You may need to add instructions to your agent to guide the output format.

#### Option 3: Add Instructions for JSON Format

For models without JSON schema support, you can include instructions in your agent to guide the output format:

```csharp
ChatClientAgent agent = chatClient.CreateAIAgent(new ChatClientAgentOptions(
    name: "HelpfulAssistant", 
    instructions: @"You are a helpful assistant. 
        When asked for person information, respond with valid JSON in this format:
        {""name"": ""string"", ""age"": number, ""occupation"": ""string""}"));

// Use with useJsonSchemaResponseFormat: false
AgentRunResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>(
    "Please provide information about John Smith, who is a 35-year-old software engineer.",
    useJsonSchemaResponseFormat: false);
```

## Running the Sample

This sample uses Azure OpenAI which supports JSON schema. Set the following environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
```

Then run:

```powershell
dotnet run
```

## Additional Resources

- [OpenAI Structured Outputs Documentation](https://platform.openai.com/docs/guides/structured-outputs)
- [Microsoft.Extensions.AI ChatResponseFormat Documentation](https://learn.microsoft.com/dotnet/api/microsoft.extensions.ai.chatresponseformat)
