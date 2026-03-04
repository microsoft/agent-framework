// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use dependency injection to register a FoundryAgentClient and use it from a hosted service.

using Microsoft.Agents.AI;
using Microsoft.Agents.AI.AzureAI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

// Create the agent using environment variable auto-discovery.
//   AZURE_AI_PROJECT_ENDPOINT - The Azure AI Foundry project endpoint URL.
//   AZURE_AI_MODEL_DEPLOYMENT_NAME - The model deployment name to use.
FoundryAgentClient agent = new(
    instructions: "You are good at telling jokes.",
    name: "JokerAgent");

// Create a host builder that we will register services with and then run.
HostApplicationBuilder builder = Host.CreateApplicationBuilder(args);

// Add the AI agent to the service collection.
builder.Services.AddSingleton<AIAgent>(agent);

// Add a sample service that will use the agent to respond to user input.
builder.Services.AddHostedService<SampleService>();

// Build and run the host.
using IHost host = builder.Build();
await host.RunAsync().ConfigureAwait(false);

/// <summary>
/// A sample service that uses an AI agent to respond to user input.
/// </summary>
internal sealed class SampleService(AIAgent agent, IHostApplicationLifetime appLifetime) : IHostedService
{
    private AgentSession? _session;

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        this._session = await agent.CreateSessionAsync(cancellationToken);
        _ = this.RunAsync(appLifetime.ApplicationStopping);
    }

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        await Task.Delay(100, cancellationToken);

        while (!cancellationToken.IsCancellationRequested)
        {
            Console.WriteLine("\nAgent: Ask me to tell you a joke about a specific topic. To exit just press Ctrl+C or enter without any input.\n");
            Console.Write("> ");
            string? input = Console.ReadLine();

            if (string.IsNullOrWhiteSpace(input))
            {
                appLifetime.StopApplication();
                break;
            }

            await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(input, this._session, cancellationToken: cancellationToken))
            {
                Console.Write(update);
            }

            Console.WriteLine();
        }
    }

    public Task StopAsync(CancellationToken cancellationToken)
    {
        Console.WriteLine("\nShutting down...");
        return Task.CompletedTask;
    }
}
