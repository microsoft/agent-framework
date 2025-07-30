// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using OpenTelemetry;
using OpenTelemetry.Trace;

const string SourceName = "OpenTelemetryAspire.ConsoleApp";

// Enable telemetry for agents
AppContext.SetSwitch("Microsoft.Extensions.AI.Agents.EnableTelemetry", true);

// Configure OpenTelemetry for Aspire dashboard
var otlpEndpoint = Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT") ?? "http://localhost:4317";

using var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .AddSource(SourceName) // Our custom activity source
    .AddSource("Microsoft.Extensions.AI.Agents") // Agent Framework telemetry
    .AddHttpClientInstrumentation() // Capture HTTP calls to OpenAI
    .AddOtlpExporter(options =>
    {
        options.Endpoint = new Uri(otlpEndpoint);
    })
    .Build();

using var activitySource = new ActivitySource(SourceName);

Console.WriteLine("=== OpenTelemetry Aspire Demo ===\n");
Console.WriteLine("This demo shows OpenTelemetry integration with the Agent Framework.\n");
Console.WriteLine("You can view the telemetry data in the Aspire Dashboard.\n");
Console.WriteLine("Type your message and press Enter. Type 'exit' to quit.\n");

// Create the chat client - try Azure OpenAI first
var configuredEndpoint = Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT") ?? "http://localhost:4317";
var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT", EnvironmentVariableTarget.Machine) ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT environment variable is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

IChatClient chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential())
        .GetChatClient(deploymentName)
        .AsIChatClient();

// Create the agent with OpenTelemetry instrumentation
var baseAgent = new ChatClientAgent(
    chatClient,
    name: "OpenTelemetryDemoAgent",
    instructions: "You are a helpful assistant that provides concise and informative responses.");

using var agent = baseAgent.WithOpenTelemetry(sourceName: SourceName);
var thread = agent.GetNewThread();

while (true)
{
    Console.Write("You: ");
    var userInput = Console.ReadLine();

    if (string.IsNullOrWhiteSpace(userInput) || userInput.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    // Create an outer span for the entire agent interaction
    using var activity = activitySource.StartActivity("Agent Interaction");
    activity?.SetTag("user.input", userInput);
    activity?.SetTag("agent.name", "OpenTelemetryDemoAgent");

    try
    {
        Console.WriteLine("Agent: Processing...");

        // Run the agent (this will create its own internal telemetry spans)
        var response = await agent.RunAsync(userInput, thread);

        Console.WriteLine($"Agent: {response.Messages.LastOrDefault()?.Text}");
        Console.WriteLine();

        activity?.SetTag("response.success", true);
        activity?.SetTag("response.message_count", response.Messages.Count);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
        Console.WriteLine();

        activity?.SetTag("response.success", false);
        activity?.SetTag("error.message", ex.Message);
        activity?.SetStatus(ActivityStatusCode.Error, ex.Message);
    }
}

Console.WriteLine("Goodbye!");
