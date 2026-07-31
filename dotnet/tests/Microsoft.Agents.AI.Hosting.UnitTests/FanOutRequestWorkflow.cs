// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Builds a workflow whose start executor, in a single superstep, both emits an external request (to a
/// <see cref="RequestPort"/>) and queues a message to a downstream executor that yields output. Used to
/// verify that resuming does not truncate the turn at the request-bearing superstep before the downstream
/// executor runs.
/// </summary>
internal static class FanOutRequestWorkflow
{
    internal const string RequestPortId = "approval";
    internal const string DownstreamPrefix = "downstream:";

    internal static Workflow Build()
    {
        var start = new FanOutExecutor("start", RequestPortId, "downstream");
        RequestPort port = RequestPort.Create<ApprovalRequest, string>(RequestPortId);
        var downstream = new DownstreamExecutor("downstream");

        return new WorkflowBuilder(start)
            .AddEdge(start, port)
            .AddEdge(start, downstream)
            .WithOutputFrom(downstream)
            .Build();
    }

    internal sealed record ApprovalRequest(string Prompt);

    private sealed class FanOutExecutor(string id, string requestPortId, string downstreamId) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string>(this.HandleAsync))
                              .SendsMessage<ApprovalRequest>()
                              .SendsMessage<string>();

        private async ValueTask HandleAsync(string input, IWorkflowContext context, CancellationToken cancellationToken = default)
        {
            // Same superstep: emit an external request AND queue downstream work.
            await context.SendMessageAsync(new ApprovalRequest(input), requestPortId, cancellationToken).ConfigureAwait(false);
            await context.SendMessageAsync(input, downstreamId, cancellationToken).ConfigureAwait(false);
        }
    }

    private sealed class DownstreamExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string>(this.HandleAsync))
                              .YieldsOutput<string>();

        private ValueTask HandleAsync(string message, IWorkflowContext context, CancellationToken cancellationToken = default)
            => context.YieldOutputAsync($"{DownstreamPrefix}{message}", cancellationToken);
    }
}
