// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;

namespace ResponsesWorkflowSample;

/// <summary>Minimal single-executor workflow body: echoes the input string as the workflow output.</summary>
internal sealed class EchoExecutor() : Executor<string, string>("EchoExecutor")
{
    public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
        ValueTask.FromResult($"echo: {message}");
}