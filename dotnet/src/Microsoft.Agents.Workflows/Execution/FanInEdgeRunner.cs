// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class FanInEdgeRunner(IRunnerContext runContext, FanInEdgeData edgeData) :
    EdgeRunner<FanInEdgeData>(runContext, edgeData),
    IStatefulEdgeRunner
{
    private FanInEdgeState _state = new(edgeData);

    protected internal override async ValueTask<DeliveryMapping?> ChaseEdgeAsync(MessageEnvelope envelope, IStepTracer? stepTracer)
    {
        Debug.Assert(!envelope.IsExternal, "FanIn edges should never be chased from external input");

        if (envelope.TargetId is not null && this.EdgeData.SinkId != envelope.TargetId)
        {
            return null;
        }

        // source.Id is guaranteed to be non-null here because source is not None.
        IEnumerable<MessageEnvelope>? releasedMessages = this._state.ProcessMessage(envelope.SourceId, envelope);
        if (releasedMessages is null)
        {
            // Not ready to process yet.
            return null;
        }

        // TODO: Filter messages based on accepted input types?
        Executor target = await this.RunContext.EnsureExecutorAsync(this.EdgeData.SinkId, stepTracer)
                                               .ConfigureAwait(false);

        return new DeliveryMapping(releasedMessages.Where(envelope => target.CanHandle(envelope.MessageType)), target);
    }

    public ValueTask<PortableValue> ExportStateAsync()
    {
        return new(new PortableValue(this._state));
    }

    public ValueTask ImportStateAsync(PortableValue state)
    {
        if (state.Is(out FanInEdgeState? importedState))
        {
            this._state = importedState;
            return default;
        }

        throw new InvalidOperationException($"Unsupported exported state type: {state.GetType()}; {this.EdgeData.Id}");
    }
}
