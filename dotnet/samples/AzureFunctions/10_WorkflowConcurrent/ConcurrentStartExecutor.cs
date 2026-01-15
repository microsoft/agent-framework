// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

internal sealed class ConcurrentStartExecutor() : Executor<string, string>("ConcurrentStartExecutor")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // do some initial parsing and validation of the message.
        // Return a polished version ith additional metadta.
        if (!message.StartsWith("Query for the agent:", StringComparison.OrdinalIgnoreCase))
        {
            message = "Query for the agent: " + message;
        }

        return ValueTask.FromResult(message);
    }
}

internal sealed class ConcurrentAggregationExecutor() : Executor<string[], string>("ConcurrentAggregationExecutor")
{
    /// <summary>
    /// Handles incoming messages from the agents and aggregates their responses.
    /// </summary>
    /// <param name="message">The messages from the parallel agents.</param>
    /// <param name="context">Workflow context for accessing workflow services and adding events.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.
    /// The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    public override ValueTask<string> HandleAsync(string[] message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Aggregate all responses from parallel executors
        string aggregatedResponse = string.Join("\n---\n", message);
        return ValueTask.FromResult($"Aggregated {message.Length} responses:\n{aggregatedResponse}");
    }
}
