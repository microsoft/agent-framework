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

var agent = persistentAgentsClient.GetAIAgent("asst_0NGYrFPfT6xMJUh2pW4SkcFC");
agent.AddCallback(new TimingCallbackMiddleware());

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
internal sealed class TimingCallbackMiddleware : CallbackMiddleware<MyCustomAgentInvokeCallbackContext>
{
    public override async Task OnProcessAsync(MyCustomAgentInvokeCallbackContext context, Func<MyCustomAgentInvokeCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        Console.WriteLine($"[TIMING] Starting invocation for agent: {context.Agent.DisplayName}");
        context.TimingStart = DateTime.UtcNow;

        try
        {
            await next(context).ConfigureAwait(false);

            if (!context.IsStreaming)
            {
                Console.WriteLine($"Response: {context.RunResult?.Messages[0].Text}");
            }
            else
            {
                // Run the streaming
                await foreach (var update in context.RunStreamResult!)
                {
                    Console.WriteLine($"Streaming update: {update.Text}");
                }
            }

            if (context.TimingStart != default)
            {
                var duration = DateTime.UtcNow - context.TimingStart;
                Console.WriteLine($"[TIMING] Completed invocation for agent: {context.Agent.DisplayName} in {duration.TotalMilliseconds:F1}ms");
            }
        }
        catch (Exception exception)
        {
            Console.WriteLine($"[TIMING] Error in invocation for agent: {context.Agent.DisplayName} - {exception.Message}");
            throw;
        }
    }
}

/// <summary>
/// Represents the context for invoking a callback in a custom AI agent, extending the base functionality of <see cref="AgentInvokeCallbackContext"/> to manage specific time properties.
/// </summary>
internal sealed class MyCustomAgentInvokeCallbackContext : AgentInvokeCallbackContext
{
    /// <summary>
    /// Specialized contexts will created by the Agent Framework injecting the generated base context.
    /// </summary>
    /// <param name="context"></param>
    public MyCustomAgentInvokeCallbackContext(AgentInvokeCallbackContext context)
        : base(context)
    {
    }

    public DateTimeOffset TimingStart { get; set; }
}
