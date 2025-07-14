// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents;
using OpenTelemetry;
using OpenTelemetry.Trace;

namespace Steps;

/// <summary>
/// Demonstrates how to use telemetry with <see cref="ChatClientAgent"/> using OpenTelemetry.
/// </summary>
public sealed class Step05_ChatClientAgent_Telemetry(ITestOutputHelper output) : AgentSample(output)
{
    /// <summary>
    /// Demonstrates OpenTelemetry tracing with Agent Framework.
    /// </summary>
    [Theory]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIChatCompletion)]
    [InlineData(ChatClientProviders.OpenAIResponses)]
    public async Task RunWithTelemetry(ChatClientProviders provider)
    {
        // Enable telemetry
        AppContext.SetSwitch("Microsoft.Extensions.AI.Agents.EnableTelemetry", true);

        // Create TracerProvider with console exporter
        string sourceName = Guid.NewGuid().ToString();

        using var tracerProvider = Sdk.CreateTracerProviderBuilder()
            .AddSource(sourceName)
            .AddConsoleExporter()
            .Build();

        // Define agent
        var agentOptions = new ChatClientAgentOptions
        {
            Name = "TelemetryAgent",
            Instructions = "You are a helpful assistant.",
        };

        using var chatClient = base.GetChatClient(provider, agentOptions);
        var baseAgent = new ChatClientAgent(chatClient, agentOptions);

        // Wrap the agent with OpenTelemetry instrumentation
        using var agent = baseAgent.WithOpenTelemetry();
        var thread = agent.GetNewThread();

        // Run agent interactions
        await agent.RunAsync("What is artificial intelligence?", thread);
        await agent.RunAsync("How does machine learning work?", thread);

        // Clean up
        await base.AgentCleanUpAsync(provider, baseAgent, thread);
    }
}
