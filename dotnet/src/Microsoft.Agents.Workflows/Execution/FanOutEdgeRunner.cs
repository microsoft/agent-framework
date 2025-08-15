// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal class FanOutEdgeRunner(IRunnerContext runContext, FanOutEdgeData edgeData) :
    EdgeRunner<FanOutEdgeData>(runContext, edgeData)
{
    private Dictionary<string, IWorkflowContext> BoundContexts { get; }
        = edgeData.SinkIds.ToDictionary(
            sinkId => sinkId,
            sinkId => runContext.Bind(sinkId));

    public async ValueTask<IEnumerable<object?>> ChaseAsync(MessageEnvelope envelope)
    {
        object message = envelope.Message;
        List<string> targets =
            this.EdgeData.PartitionAssigner == null
                ? this.EdgeData.SinkIds
                : this.EdgeData.PartitionAssigner(message, this.BoundContexts.Count)
                               .Select(i => this.EdgeData.SinkIds[i]).ToList();

        IEnumerable<string> filteredTargets = envelope.TargetId != null
                                            ? targets.Where(IsValidTarget)
                                            : targets;

        object?[] result = await Task.WhenAll(filteredTargets.Select(ProcessTargetAsync)).ConfigureAwait(false);
        return result.Where(r => r is not null);

        async Task<object?> ProcessTargetAsync(string targetId)
        {
            Executor executor = await this.RunContext.EnsureExecutorAsync(targetId)
                                                         .ConfigureAwait(false);

            if (executor.CanHandle(message.GetType()))
            {
                return await executor.ExecuteAsync(message, envelope.MessageType, this.BoundContexts[targetId])
                                     .ConfigureAwait(false);
            }

            return null;
        }

        bool IsValidTarget(string targetId)
        {
            return envelope.TargetId == null || targetId == envelope.TargetId;
        }
    }
}
