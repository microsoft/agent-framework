// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;

/// <summary>Builds a trivial single-executor echo workflow for target-neutrality tests.</summary>
internal static class WorkflowFactory
{
    public static Workflow Echo()
    {
        var echo = new EchoExecutor();
        return new WorkflowBuilder(echo).WithOutputFrom(echo).Build();
    }

    private sealed class EchoExecutor() : Executor<string, string>("EchoExecutor")
    {
        public override ValueTask<string> HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default) =>
            ValueTask.FromResult($"echo: {message}");
    }
}
