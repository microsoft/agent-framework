// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to configure ChatClientAgent to produce structured output.

using System.ComponentModel;
using System.Text.Json;
using System.Text.Json.Serialization;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;
using SampleApp;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

string endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create chat client to be used by chat client agents.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
ChatClient chatClient = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
        .GetChatClient(deploymentName);

// Demonstrates how to work with structured output via ResponseFormat with the non-generic RunAsync method.
// This approach is useful when:
// a. Structured output is used for inter-agent communication, where one agent produces structured output
//    and passes it as text to another agent as input, without the need for the caller to directly work with the structured output.
// b. The type of the structured output is not known at compile time, so the generic RunAsync<T> method cannot be used.
// c. The type of the structured output is represented by JSON schema only, without a corresponding class or type in the code.
await UseStructuredOutputWithResponseFormatAsync(chatClient);

// Demonstrates how to work with structured output via the generic RunAsync<T> method.
// This approach is useful when the caller needs to directly work with the structured output in the code
// via an instance of the corresponding class or type and the type is known at compile time.
await UseStructuredOutputWithRunAsync(chatClient);

// Demonstrates how to work with structured output when streaming using the RunStreamingAsync method.
await UseStructuredOutputWithRunStreamingAsync(chatClient);

// Demonstrates how to add structured output support to agents that don't natively support it using the structured output middleware.
// This approach is useful when working with agents that don't support structured output natively, or agents using models
// that don't have the capability to produce structured output, allowing you to still leverage structured output features by transforming
// the text output from the agent into structured data using a chat client.
await UseStructuredOutputWithMiddlewareAsync(chatClient);

static async Task UseStructuredOutputWithResponseFormatAsync(ChatClient chatClient)
{
    Console.WriteLine("=== Structured Output with ResponseFormat ===");

    // Create the agent
    AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions()
    {
        Name = "HelpfulAssistant",
        ChatOptions = new()
        {
            Instructions = "You are a helpful assistant.",
            // Specify CityInfo as the type parameter of ForJsonSchema to indicate the expected structured output from the agent.
            ResponseFormat = Microsoft.Extensions.AI.ChatResponseFormat.ForJsonSchema<CityInfo>()
        }
    });

    // Invoke the agent with some unstructured input to extract the structured information from.
    AgentResponse response = await agent.RunAsync("Provide information about the capital of France.");

    // Access the structured output via the Text property of the agent response as JSON in scenarios when JSON as text is required
    // and no object instance is needed (e.g., for logging, forwarding to another service, or storing in a database).
    Console.WriteLine("Assistant Output (JSON):");
    Console.WriteLine(response.Text);
    Console.WriteLine();

    // Deserialize the JSON text to work with the structured object in scenarios when you need to access properties,
    // perform operations, or pass the data to methods that require the typed object instance.
    CityInfo cityInfo = JsonSerializer.Deserialize<CityInfo>(response.Text)!;

    Console.WriteLine("Assistant Output (Deserialized):");
    Console.WriteLine($"Name: {cityInfo.Name}");
    Console.WriteLine();
}

static async Task UseStructuredOutputWithRunAsync(ChatClient chatClient)
{
    Console.WriteLine("=== Structured Output with RunAsync<T> ===");

    // Create the agent
    AIAgent agent = chatClient.AsAIAgent(name: "HelpfulAssistant", instructions: "You are a helpful assistant.");

    // Set CityInfo as the type parameter of RunAsync method to specify the expected structured output from the agent and invoke it with some unstructured input.
    AgentResponse<CityInfo> response = await agent.RunAsync<CityInfo>("Provide information about the capital of France.");

    // Access the structured output via the Result property of the agent response.
    CityInfo cityInfo = response.Result;

    Console.WriteLine("Assistant Output:");
    Console.WriteLine($"Name: {cityInfo.Name}");
    Console.WriteLine();
}

static async Task UseStructuredOutputWithRunStreamingAsync(ChatClient chatClient)
{
    Console.WriteLine("=== Structured Output with RunStreamingAsync ===");

    // Create the agent
    AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions()
    {
        Name = "HelpfulAssistant",
        ChatOptions = new()
        {
            Instructions = "You are a helpful assistant.",
            // Specify CityInfo as the type parameter of ForJsonSchema to indicate the expected structured output from the agent.
            ResponseFormat = Microsoft.Extensions.AI.ChatResponseFormat.ForJsonSchema<CityInfo>()
        }
    });

    // Invoke the agent with some unstructured input while streaming, to extract the structured information from.
    IAsyncEnumerable<AgentResponseUpdate> updates = agent.RunStreamingAsync("Provide information about the capital of France.");

    // Assemble all the parts of the streamed output.
    AgentResponse nonGenericResponse = await updates.ToAgentResponseAsync();

    // Access the structured output by deserializing JSON in the Text property.
    CityInfo cityInfo = JsonSerializer.Deserialize<CityInfo>(nonGenericResponse.Text)!;

    Console.WriteLine("Assistant Output:");
    Console.WriteLine($"Name: {cityInfo.Name}");
    Console.WriteLine();
}

static async Task UseStructuredOutputWithMiddlewareAsync(ChatClient chatClient)
{
    Console.WriteLine("=== Structured Output with UseStructuredOutput Middleware ===");

    // Create chat client that will transform the agent text response into structured output.
    IChatClient meaiChatClient = chatClient.AsIChatClient();

    // Create the agent
    AIAgent agent = meaiChatClient.AsAIAgent(name: "HelpfulAssistant", instructions: "You are a helpful assistant.");

    // Add structured output middleware via UseStructuredOutput method to add structured output support to the agent.
    // This middleware transforms the agent's text response into structured data using a chat client.
    // Since our agent does support structured output natively, we will add a middleware that removes ResponseFormat
    //  from the AgentRunOptions to emulate an agent that doesn't support structured output natively
    agent = agent
        .AsBuilder()
        .UseStructuredOutput(meaiChatClient)
        .Use(ResponseFormatRemovalMiddleware, null)
        .Build();

    // Set CityInfo as the type parameter of RunAsync method to specify the expected structured output from the agent and invoke it with some unstructured input.
    AgentResponse<CityInfo> response = await agent.RunAsync<CityInfo>("Provide information about the capital of France.");

    // Access the structured output via the Result property of the agent response.
    CityInfo cityInfo = response.Result;

    Console.WriteLine("Assistant Output:");
    Console.WriteLine($"Name: {cityInfo.Name}");
    Console.WriteLine();
}

static Task<AgentResponse> ResponseFormatRemovalMiddleware(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
{
    // Remove any ResponseFormat from the options to emulate an agent that doesn't support structured output natively.
    options = options?.Clone();
    options?.ResponseFormat = null;

    return innerAgent.RunAsync(messages, session, options, cancellationToken);
}

namespace SampleApp
{
    /// <summary>
    /// Represents information about a city, including its name.
    /// </summary>
    [Description("Information about a city")]
    public sealed class CityInfo
    {
        [JsonPropertyName("name")]
        public string? Name { get; set; }
    }
}
