// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to use dependency injection to register an AIAgent and use it from a hosted service with a user input chat loop.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

string endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

const string JokerInstructions = "You are good at telling jokes.";
const string JokerName = "JokerAgent";

// Create a host builder that we will register services with and then run.
HostApplicationBuilder builder = Host.CreateApplicationBuilder(args);

// Add the agents client to the service collection.
builder.Services.AddSingleton((sp) => new AIProjectClient(new Uri(endpoint), new AzureCliCredential()));

// Add the AI agent to the service collection.
builder.Services.AddSingleton<AIAgent>((sp)
    => sp.GetRequiredService<AIProjectClient>()
        .CreateAIAgent(name: JokerName, model: deploymentName, instructions: JokerInstructions));

// Add a sample service that will use the agent to respond to user input.
builder.Services.AddHostedService<SampleService>();

// Build and run the host.
using IHost host = builder.Build();
await host.RunAsync().ConfigureAwait(false);

/// <summary>
/// A sample service that uses an AI agent to respond to user input.
/// </summary>
internal sealed class SampleService(AIProjectClient client, AIAgent agent, IHostApplicationLifetime appLifetime) : IHostedService
{
    private AgentThread? _thread;

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        // Create a thread that will be used for the entirety of the service lifetime so that the user can ask follow up questions.
        this._thread = agent.GetNewThread();
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
            string? input = Console.ReadLine();

            // If the user enters no input, signal the application to shut down.
            if (string.IsNullOrWhiteSpace(input))
            {
                appLifetime.StopApplication();
                break;
            }

            // Stream the output to the console as it is generated.
            await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(input, this._thread, cancellationToken: cancellationToken))
            {
                Console.Write(update);
            }

            Console.WriteLine();
        }
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        Console.WriteLine("\nDeleting agent ...");
        await client.Agents.DeleteAgentAsync(agent.Name, cancellationToken).ConfigureAwait(false);
    }
}
