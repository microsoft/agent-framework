// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Builds a non-chat-protocol workflow whose single executor keeps a running count in workflow state and
/// yields <c>count:N</c>. Because the count is checkpointed, a genuine resume observes the accumulated value
/// (for example <c>count:2</c> on the second turn), whereas a fresh run restarts at <c>count:1</c>. Used to
/// prove that a turn actually resumed from a prior checkpoint rather than starting over.
/// </summary>
internal static class CountingWorkflow
{
    internal static Workflow Build()
    {
        var counter = new CountingExecutor("counter");
        return new WorkflowBuilder(counter)
            .WithOutputFrom(counter)
            .Build();
    }

    private sealed class CountingExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string>(this.HandleAsync))
                              .YieldsOutput<string>();

        private async ValueTask HandleAsync(string input, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            int count = await context.ReadOrInitStateAsync("count", () => 0, cancellationToken).ConfigureAwait(false);
            count++;
            await context.QueueStateUpdateAsync("count", count, cancellationToken: cancellationToken).ConfigureAwait(false);
            await context.YieldOutputAsync($"count:{count}", cancellationToken).ConfigureAwait(false);
        }
    }
}
