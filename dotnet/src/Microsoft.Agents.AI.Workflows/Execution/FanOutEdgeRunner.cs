// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class FanOutEdgeRunner(IRunnerContext runContext, FanOutEdgeData edgeData) :
    EdgeRunner<FanOutEdgeData>(runContext, edgeData)
{
    private Dictionary<string, IWorkflowContext> BoundContexts { get; }
        = edgeData.SinkIds.ToDictionary(
            sinkId => sinkId,
            runContext.Bind);

    protected internal override async ValueTask<DeliveryMapping?> ChaseEdgeAsync(MessageEnvelope envelope, IStepTracer? stepTracer)
    {
        object message = envelope.Message;
        IEnumerable<string> targetIds =
            this.EdgeData.EdgeAssigner is null
                ? this.EdgeData.SinkIds
                : this.EdgeData.EdgeAssigner(message, this.BoundContexts.Count)
                               .Select(i => this.EdgeData.SinkIds[i]);

        Executor[] result = await Task.WhenAll(targetIds.Where(IsValidTarget)
                                                        .Select(tid => this.RunContext.EnsureExecutorAsync(tid, stepTracer)
                                                        .AsTask()))
                                      .ConfigureAwait(false);

        if (result.Length == 0)
        {
            return null;
        }

        IEnumerable<Executor> validTargets = result.Where(t => t.CanHandle(envelope.MessageType));
        return new DeliveryMapping(envelope, validTargets);

        bool IsValidTarget(string targetId)
        {
            return envelope.TargetId is null || targetId == envelope.TargetId;
        }
    }
}
