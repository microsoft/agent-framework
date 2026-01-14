// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace SingleAgent;

/// <summary>
/// Routes survey responses to appropriate teams based on rating and category.
/// </summary>
public sealed class ResponseRouterExecutor() : Executor<string, string>("ResponseRouterExecutor")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (message.Contains("billing", StringComparison.OrdinalIgnoreCase))
        {
            return ValueTask.FromResult("Routed to Billing Team");
        }
        else if (message.Contains("technical", StringComparison.OrdinalIgnoreCase))
        {
            return ValueTask.FromResult("Routed to Technical Support Team");
        }
        else
        {
            return ValueTask.FromResult("Routed to General Support Team");
        }
    }
}
