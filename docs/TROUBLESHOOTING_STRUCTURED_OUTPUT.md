# Troubleshooting Structured Output

This guide helps you diagnose and resolve issues with structured output when using AI agents.

## Symptoms

- **Empty responses** when using `RunAsync<T>()` method
- **Null values** in the `Result` property of `AgentRunResponse<T>`
- **Timeout or hanging** during structured output calls
- **Unexpected JSON format** that doesn't match your schema

## Root Cause

The most common cause is **model incompatibility with JSON schema**. The Agent Framework's `RunAsync<T>()` method defaults to using `useJsonSchemaResponseFormat: true`, which requires the underlying model to support JSON schema-based structured output natively.

## Models That Support JSON Schema

The following models have native support for structured output with JSON schema:

### OpenAI Models
- GPT-4o and GPT-4o-mini (versions 2024-08-06 and later)
- GPT-4 Turbo (certain versions)

### Azure OpenAI Models
- GPT-4o and GPT-4o-mini (versions 2024-08-06 and later)
- GPT-4 Turbo (certain versions, when deployed in Azure)

## Models That Do NOT Support JSON Schema

### Ollama Models
**All Ollama models** do not support native JSON schema validation, including:
- gpt-oss
- llama3 and llama3.1
- phi3
- mistral
- Any other model running on Ollama

### Other Models
- Older OpenAI models (pre-2024)
- Most open-source models without specific JSON schema support
- Many third-party model providers

## Solutions

### Solution 1: Use a Compatible Model

Switch to a model that supports JSON schema. For example:
- Use Azure OpenAI GPT-4o-mini instead of Ollama gpt-oss
- Use OpenAI GPT-4o instead of a local model

### Solution 2: Disable JSON Schema Format

When using models without JSON schema support, set `useJsonSchemaResponseFormat: false`:

```csharp
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

// Create your agent (example with Ollama)
IChatClient chatClient = new OllamaApiClient(new Uri(endpoint), modelName);
ChatClientAgent agent = chatClient.CreateAIAgent(
    instructions: "You are a helpful assistant. Always respond with valid JSON in the format: {\"name\": \"string\", \"age\": number, \"occupation\": \"string\"}",
    name: "Assistant");

// Call with useJsonSchemaResponseFormat: false
AgentRunResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>(
    "Please provide information about John Smith, who is a 35-year-old software engineer.",
    useJsonSchemaResponseFormat: false);

// Access the result
Console.WriteLine($"Name: {response.Result?.Name}");
Console.WriteLine($"Age: {response.Result?.Age}");
Console.WriteLine($"Occupation: {response.Result?.Occupation}");
```

### Solution 3: Enhance Your Instructions

When not using JSON schema, include detailed formatting instructions in your agent's prompt:

```csharp
const string instructions = """
    You are a helpful assistant that extracts person information from text.
    IMPORTANT: Always respond with valid JSON and ONLY JSON (no markdown, no code blocks).
    The JSON must contain exactly these fields:
    - "name": string (the person's full name)
    - "age": number (the person's age as an integer)
    - "occupation": string (the person's job or profession)
    
    Example response format:
    {"name": "John Doe", "age": 30, "occupation": "Engineer"}
    """;

ChatClientAgent agent = chatClient.CreateAIAgent(instructions, "Assistant");
```

## Best Practices

1. **Check model capabilities** before using structured output
2. **Always use `useJsonSchemaResponseFormat: false`** with Ollama and other non-compatible models
3. **Provide clear instructions** about the expected JSON format in your agent's instructions
4. **Test with sample data** to ensure the format is correct before production use
5. **Handle null values** gracefully in case the model doesn't produce valid JSON
6. **Add error handling** for JSON parsing failures

## Example: Working with Ollama

Here's a complete example showing proper structured output usage with Ollama:

```csharp
using System.Text.Json.Serialization;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OllamaSharp;

// Define your data model
class PersonInfo
{
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    [JsonPropertyName("age")]
    public int? Age { get; set; }

    [JsonPropertyName("occupation")]
    public string? Occupation { get; set; }
}

// Set up Ollama client
var endpoint = Environment.GetEnvironmentVariable("OLLAMA_ENDPOINT") ?? "http://localhost:11434";
var modelName = Environment.GetEnvironmentVariable("OLLAMA_MODEL_NAME") ?? "gpt-oss";

// Create chat client and agent with detailed instructions
IChatClient chatClient = new OllamaApiClient(new Uri(endpoint), modelName);
ChatClientAgent agent = chatClient.CreateAIAgent(
    instructions: """
        You are a helpful assistant that extracts person information.
        Always respond with valid JSON containing 'name', 'age', and 'occupation' fields.
        Do not include markdown formatting or code blocks, just the raw JSON.
        """,
    name: "PersonExtractor");

// Use structured output with useJsonSchemaResponseFormat: false
try
{
    AgentRunResponse<PersonInfo> response = await agent.RunAsync<PersonInfo>(
        "Please provide information about John Smith, who is a 35-year-old software engineer.",
        useJsonSchemaResponseFormat: false);

    if (response.Result != null)
    {
        Console.WriteLine($"Name: {response.Result.Name}");
        Console.WriteLine($"Age: {response.Result.Age}");
        Console.WriteLine($"Occupation: {response.Result.Occupation}");
    }
    else
    {
        Console.WriteLine("Warning: Received null result");
    }
}
catch (Exception ex)
{
    Console.WriteLine($"Error: {ex.Message}");
}
```

## Debugging Tips

1. **Enable logging** to see the actual prompts and responses
2. **Test without structured output first** to verify the model is working
3. **Check the raw response text** before deserialization
4. **Try simpler schemas** if complex ones fail
5. **Compare with working samples** in the repository

## Related Documentation

- [Structured Output Sample](../dotnet/samples/GettingStarted/Agents/Agent_Step05_StructuredOutput/README.md)
- [Ollama Agent Sample](../dotnet/samples/GettingStarted/AgentProviders/Agent_With_Ollama/README.md)
- [Agent Run Response Design Decision](./decisions/0001-agent-run-response.md)

## Getting Help

If you're still experiencing issues after trying these solutions:

1. Check the [GitHub Issues](https://github.com/microsoft/agent-framework/issues) for similar problems
2. Review the [FAQ](./FAQS.md) for common questions
3. Open a new issue with:
   - The model you're using (provider and version)
   - Your code snippet
   - The actual error or unexpected behavior
   - What you've already tried
