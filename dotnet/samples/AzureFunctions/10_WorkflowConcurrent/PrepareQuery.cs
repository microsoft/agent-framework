// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

internal sealed class PrepareQuery() : Executor<string, string>("PrepareQuery")
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

internal sealed class ResultAggregator() : Executor<string[], string>("ResultAggregator")
{
    public override ValueTask<string> HandleAsync(string[] message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        // Aggregate all responses from parallel executors.
        string aggregatedResponse = string.Join("\n---\n", message);
        return ValueTask.FromResult($"Aggregated {message.Length} responses:\n{aggregatedResponse}");
    }
}
