// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable RCS1110 // Declare type inside namespace
#pragma warning disable CA1812 // Declare type inside namespace

using System;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;

// Create a logger factory for the sample
using var loggerFactory = LoggerFactory.Create(builder =>
    builder.AddConsole().SetMinimumLevel(LogLevel.Information));

// Get Azure AI Foundry configuration from environment variables
var endpoint = Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_ENDPOINT") ?? throw new InvalidOperationException("AZURE_FOUNDRY_PROJECT_ENDPOINT is not set.");
var model = System.Environment.GetEnvironmentVariable("AZURE_FOUNDRY_PROJECT_MODEL_ID") ?? "gpt-4o-mini";

// Get a client to create/retrieve server side agents with
var persistentAgentsClient = new PersistentAgentsClient(endpoint, new AzureCliCredential());

// Example 3: Agent with custom middleware
Console.WriteLine("=== Example 3: Agent with custom middleware ===");

var agent = persistentAgentsClient.CreateAIAgent(model)
    .WithCallbacks(builder =>
    {
        builder.AddCallback(new TimingCallbackMiddleware());
    });

var customResponse = await agent.RunAsync("Tell me a joke.");

// Example 4: Streaming with middleware
Console.WriteLine("=== Example 4: Streaming with middleware ===");
await foreach (var update in agent.RunStreamingAsync("Count from 1 to 3."))
{
    if (update.Text is not null)
    {
        Console.Write(update.Text);
    }
}
Console.WriteLine();
Console.WriteLine();

// Cleanup
await persistentAgentsClient.Administration.DeleteAgentAsync(agent.Id);

Console.WriteLine("Callback middleware demonstration completed!");

/// <summary>
/// A custom callback middleware that measures timing.
/// </summary>
internal sealed class TimingCallbackMiddleware : CallbackMiddleware<AgentInvokeCallbackContext>
{
    public override async Task OnProcessAsync(AgentInvokeCallbackContext context, Func<AgentInvokeCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        Console.WriteLine($"[TIMING] Starting invocation for agent: {context.Agent.DisplayName}");
        var timingStart = DateTime.UtcNow;

        try
        {
            await next(context).ConfigureAwait(false);

            if (!context.IsStreaming)
            {
                Console.WriteLine($"Response: {context.RunResponse?.Messages[0].Text}");
            }
            else
            {
                // Run the streaming
                await foreach (var update in context.RunStreamingResponse!)
                {
                    Console.WriteLine($"Streaming update: {update.Text}");
                }
            }

            var duration = DateTime.UtcNow - timingStart;
            Console.WriteLine($"[TIMING] Completed invocation for agent: {context.Agent.DisplayName} in {duration.TotalMilliseconds:F1}ms");
        }
        catch (Exception exception)
        {
            Console.WriteLine($"[TIMING] Error in invocation for agent: {context.Agent.DisplayName} - {exception.Message}");
            throw;
        }
    }
}
