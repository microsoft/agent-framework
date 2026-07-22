// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Builds a minimal human-in-the-loop workflow whose start executor forwards its input to a
/// <see cref="RequestPort"/>, so the workflow emits a <see cref="RequestInfoEvent"/> and halts awaiting an
/// external response. Used to verify that resuming such a workflow does not block indefinitely.
/// </summary>
internal static class ApprovalGateWorkflow
{
    internal const string RequestPortId = "approval";

    internal static Workflow Build()
    {
        var gate = new ApprovalGateExecutor("gate", RequestPortId);
        RequestPort port = RequestPort.Create<ApprovalRequest, string>(RequestPortId);
        var finalize = new FinalizeExecutor("finalize");

        return new WorkflowBuilder(gate)
            .AddEdge(gate, port)
            .AddEdge(port, finalize)
            .WithOutputFrom(finalize)
            .Build();
    }

    internal sealed record ApprovalRequest(string Prompt);

    private sealed class ApprovalGateExecutor(string id, string requestPortId) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string>(this.HandleAsync))
                              .SendsMessage<ApprovalRequest>();

        private ValueTask HandleAsync(string input, IWorkflowContext context, CancellationToken cancellationToken = default)
            => context.SendMessageAsync(new ApprovalRequest(input), requestPortId, cancellationToken);
    }

    private sealed class FinalizeExecutor(string id) : Executor(id)
    {
        protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
            => protocolBuilder.ConfigureRoutes(routeBuilder => routeBuilder.AddHandler<string>(this.HandleAsync))
                              .YieldsOutput<string>();

        private ValueTask HandleAsync(string approval, IWorkflowContext context, CancellationToken cancellationToken = default)
            => context.YieldOutputAsync($"approved:{approval}", cancellationToken);
    }
}
