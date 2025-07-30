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
    [InlineData(ChatClientProviders.AzureAIAgentsPersistent)]
    [InlineData(ChatClientProviders.AzureOpenAI)]
    [InlineData(ChatClientProviders.OpenAIAssistant)]
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

        // Define agent options
        var agentOptions = new ChatClientAgentOptions(name: "TelemetryAgent", instructions: "You are a helpful assistant.");

        // Create the server-side agent Id when applicable (depending on the provider).
        agentOptions.Id = await base.AgentCreateAsync(provider, agentOptions);

        using var chatClient = base.GetChatClient(provider, agentOptions);
        var baseAgent = new ChatClientAgent(chatClient, agentOptions);

        // Wrap the agent with OpenTelemetry instrumentation
        using var agent = baseAgent.WithOpenTelemetry(sourceName: sourceName);
        var thread = agent.GetNewThread();

        // Run agent interactions
        await agent.RunAsync("What is artificial intelligence?", thread);
        await agent.RunAsync("How does machine learning work?", thread);

        // Clean up
        await base.AgentCleanUpAsync(provider, baseAgent, thread);
    }
}
