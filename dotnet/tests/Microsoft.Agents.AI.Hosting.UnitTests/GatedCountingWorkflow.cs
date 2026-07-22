// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Builds a non-chat-protocol workflow whose executor signals when it starts and then blocks on a
/// test-controlled gate before finishing. This lets a test hold a turn "inside" the workflow and observe
/// whether a second, concurrent turn for the same holder is allowed to run at the same time.
/// </summary>
internal static class GatedCountingWorkflow
{
    internal static Workflow Build(SemaphoreSlim entered, Task release)
    {
        var gated = new GatedExecutor("gated", entered, release);
        return new WorkflowBuilder(gated)
            .WithOutputFrom(gated)
            .Build();
    }

    private sealed class GatedExecutor(string id, SemaphoreSlim entered, Task release) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string>(this.HandleAsync))
                              .YieldsOutput<string>();

        private async ValueTask HandleAsync(string input, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            // Signal that this turn has started running inside the workflow, then wait for the test to release.
            entered.Release();
            await release.ConfigureAwait(false);

            int count = await context.ReadOrInitStateAsync("count", () => 0, cancellationToken).ConfigureAwait(false);
            count++;
            await context.QueueStateUpdateAsync("count", count, cancellationToken: cancellationToken).ConfigureAwait(false);
            await context.YieldOutputAsync($"count:{count}", cancellationToken).ConfigureAwait(false);
        }
    }
}
