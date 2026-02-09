// Copyright (c) Microsoft. All rights reserved.
// Description: Fan-out/fan-in parallel execution with concurrent AI agents.
// Docs: https://learn.microsoft.com/agent-framework/workflows/overview

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

namespace WorkflowSamples.Concurrent;

// <concurrent_workflow>
/// <summary>
/// Demonstrates concurrent execution using fan-out and fan-in patterns.
/// Two AI agents (Physicist and Chemist) answer the same question in parallel,
/// then an aggregation executor combines their responses.
/// </summary>
public static class Program
{
    private static async Task Main()
    {
        // Set up the Azure OpenAI client
        var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT") ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
        var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
        var chatClient = new AzureOpenAIClient(new Uri(endpoint), new AzureCliCredential()).GetChatClient(deploymentName).AsIChatClient();

        // Create the executors
        ChatClientAgent physicist = new(
            chatClient,
            name: "Physicist",
            instructions: "You are an expert in physics. You answer questions from a physics perspective."
        );
        ChatClientAgent chemist = new(
            chatClient,
            name: "Chemist",
            instructions: "You are an expert in chemistry. You answer questions from a chemistry perspective."
        );
        var startExecutor = new ConcurrentStartExecutor();
        var aggregationExecutor = new ConcurrentAggregationExecutor();

        // Build the workflow with fan-out and fan-in edges
        var workflow = new WorkflowBuilder(startExecutor)
            .AddFanOutEdge(startExecutor, [physicist, chemist])
            .AddFanInEdge([physicist, chemist], aggregationExecutor)
            .WithOutputFrom(aggregationExecutor)
            .Build();

        // Execute the workflow in streaming mode
        await using StreamingRun run = await InProcessExecution.StreamAsync(workflow, input: "What is temperature?");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync())
        {
            if (evt is WorkflowOutputEvent output)
            {
                Console.WriteLine($"Workflow completed with results:\n{output.Data}");
            }
        }
    }
}
// </concurrent_workflow>

// <concurrent_start_executor>
/// <summary>
/// Executor that starts concurrent processing by broadcasting messages to agents.
/// </summary>
internal sealed partial class ConcurrentStartExecutor() :
    Executor("ConcurrentStartExecutor")
{
    [MessageHandler]
    public async ValueTask HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await context.SendMessageAsync(new ChatMessage(ChatRole.User, message), cancellationToken: cancellationToken);
        await context.SendMessageAsync(new TurnToken(emitEvents: true), cancellationToken: cancellationToken);
    }
}
// </concurrent_start_executor>

// <concurrent_aggregation_executor>
/// <summary>
/// Executor that aggregates results from concurrent agents.
/// </summary>
internal sealed class ConcurrentAggregationExecutor() :
    Executor<List<ChatMessage>>("ConcurrentAggregationExecutor")
{
    private readonly List<ChatMessage> _messages = [];

    public override async ValueTask HandleAsync(List<ChatMessage> message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._messages.AddRange(message);

        if (this._messages.Count == 2)
        {
            var formattedMessages = string.Join(Environment.NewLine, this._messages.Select(m => $"{m.AuthorName}: {m.Text}"));
            await context.YieldOutputAsync(formattedMessages, cancellationToken);
        }
    }
}
// </concurrent_aggregation_executor>
