// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable CA1812

// This sample shows how to use dependency injection to register an AIAgent and use it from a hosted service with a user input chat loop.

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

// Create a host builder that we will register services with and then run.
HostApplicationBuilder builder = Host.CreateApplicationBuilder(args);

// Add agent options to the service collection.
const string JokerName = "Joker";
const string JokerInstructions = "You are good at telling jokes.";
builder.Services.AddSingleton(new ChatClientAgentOptions(JokerInstructions, JokerName));

// Add a chat client to the service collection.
builder.Services.AddKeyedChatClient("AzureOpenAI", (sp) => new AzureOpenAIClient(
    new Uri(endpoint),
    new AzureCliCredential())
        .GetChatClient(deploymentName)
        .AsIChatClient());

// Add the AI agent to the service collection.
builder.Services.AddSingleton<AIAgent>((sp) => new ChatClientAgent(
    chatClient: sp.GetRequiredKeyedService<IChatClient>("AzureOpenAI"),
    options: sp.GetRequiredService<ChatClientAgentOptions>()));

// Add a sample service that will use the agent to respond to user input.
builder.Services.AddHostedService<SampleService>();

// Create a cancellation token and source to pass to the sample service that can
// be used to signal shutdown of the application.
CancellationTokenSource appShutdownCancellationTokenSource = new();
CancellationToken appShutdownCancellationToken = appShutdownCancellationTokenSource.Token;
builder.Services.AddKeyedSingleton("AppShutdown", appShutdownCancellationTokenSource);

// Build and run the host.
using IHost host = builder.Build();
await host.RunAsync(appShutdownCancellationToken).ConfigureAwait(false);

/// <summary>
/// A sample service that uses an AI agent to respond to user input.
/// </summary>
internal sealed class SampleService(AIAgent agent, [FromKeyedServices("AppShutdown")] CancellationTokenSource appShutdownCancellationTokenSource) : IHostedService
{
    private AgentThread? _thread;

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        // Create a thread that will be used for the entirety of the service lifetime so that the user can ask follow up questions.
        this._thread = agent.GetNewThread();
        _ = this.RunAsync(cancellationToken);
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
                appShutdownCancellationTokenSource.Cancel();
                break;
            }

            // Stream the output to the console as it is generated.
            await foreach (var update in agent.RunStreamingAsync(input, this._thread, cancellationToken: cancellationToken))
            {
                Console.Write(update);
            }

            Console.WriteLine();
        }
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
}
