// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CA1812

// Dependency Injection — Register and resolve agents via DI
//
// This sample shows how to use dependency injection to register an
// AIAgent and consume it from a hosted service with a chat loop.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

var endpoint = Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("FOUNDRY_PROJECT_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("FOUNDRY_MODEL") ?? "gpt-5.4-mini";

// Create a host builder that we will register services with and then run.
HostApplicationBuilder builder = Host.CreateApplicationBuilder(args);

// Create the AI agent from the Azure AI Foundry project client.
// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient aiProjectClient = new(new Uri(endpoint), new DefaultAzureCredential());
AIAgent agent = aiProjectClient.AsAIAgent(model: deploymentName, name: "Joker", instructions: "You are good at telling jokes.");
builder.Services.AddSingleton(agent);

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
        // Create a session that will be used for the entirety of the service lifetime so that the user can ask follow up questions.
        this._session = await agent.CreateSessionAsync(cancellationToken);
        _ = this.RunAsync(appLifetime.ApplicationStopping);
    }

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        // Delay a little to allow the service to finish starting.
        await Task.Delay(100, cancellationToken);

        while (!cancellationToken.IsCancellationRequested)
        {
            Console.WriteLine("\nAgent: Ask me to tell you a joke about a specific topic. To exit just press Ctrl+C or enter without any input.\n");
            Console.Write("> ");
            var input = Console.ReadLine();

            // If the user enters no input, signal the application to shut down.
            if (string.IsNullOrWhiteSpace(input))
            {
                appLifetime.StopApplication();
                break;
            }

            // Stream the output to the console as it is generated.
            await foreach (var update in agent.RunStreamingAsync(input, this._session, cancellationToken: cancellationToken))
            {
                Console.Write(update);
            }

            Console.WriteLine();
        }
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
}
