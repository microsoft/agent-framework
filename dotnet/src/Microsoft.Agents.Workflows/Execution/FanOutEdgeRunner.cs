// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class FanOutEdgeRunner(IRunnerContext runContext, FanOutEdgeData edgeData) :
    EdgeRunner<FanOutEdgeData>(runContext, edgeData)
{
    private Dictionary<string, IWorkflowContext> BoundContexts { get; }
        = edgeData.SinkIds.ToDictionary(
            sinkId => sinkId,
            runContext.Bind);

    public async ValueTask<IEnumerable<object?>> ChaseAsync(MessageEnvelope envelope, IStepTracer? tracer)
    {
        object message = envelope.Message;
        List<string> targets =
            this.EdgeData.EdgeAssigner is null
                ? this.EdgeData.SinkIds
                : this.EdgeData.EdgeAssigner(message, this.BoundContexts.Count)
                               .Select(i => this.EdgeData.SinkIds[i]).ToList();

        IEnumerable<string> filteredTargets =
            envelope.TargetId is not null
                ? targets.Where(IsValidTarget)
                : targets;

        object?[] result = await Task.WhenAll(filteredTargets.Select(ProcessTargetAsync)).ConfigureAwait(false);
        return result.Where(r => r is not null);

        async Task<object?> ProcessTargetAsync(string targetId)
        {
            Executor executor = await this.RunContext.EnsureExecutorAsync(targetId, tracer)
                                                         .ConfigureAwait(false);

            if (executor.CanHandle(message.GetType()))
            {
                tracer?.TraceActivated(executor.Id);
                return await executor.ExecuteAsync(message, envelope.MessageType, this.BoundContexts[targetId])
                                     .ConfigureAwait(false);
            }

            return null;
        }

        bool IsValidTarget(string targetId)
        {
            return envelope.TargetId is null || targetId == envelope.TargetId;
        }
    }
}
