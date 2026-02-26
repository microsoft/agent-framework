// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Observability;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class FanInEdgeRunner(IRunnerContext runContext, FanInEdgeData edgeData) :
    EdgeRunner<FanInEdgeData>(runContext, edgeData),
    IStatefulEdgeRunner
{
    private FanInEdgeState _state = new(edgeData);

    protected internal override async ValueTask<DeliveryMapping?> ChaseEdgeAsync(MessageEnvelope envelope, IStepTracer? stepTracer, CancellationToken cancellationToken)
    {
        Debug.Assert(!envelope.IsExternal, "FanIn edges should never be chased from external input");

        using var activity = this.StartActivity();
        activity?
            .SetTag(Tags.EdgeGroupType, nameof(FanInEdgeRunner))
            .SetTag(Tags.MessageTargetId, this.EdgeData.SinkId);

        if (envelope.TargetId is not null && this.EdgeData.SinkId != envelope.TargetId)
        {
            activity?.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.DroppedTargetMismatch);
            return null;
        }

        // source.Id is guaranteed to be non-null here because source is not None.
        List<IGrouping<ExecutorIdentity, MessageEnvelope>>? releasedMessages = this._state.ProcessMessage(envelope.SourceId, envelope)?.ToList();
        if (releasedMessages is null)
        {
            // Not ready to process yet.
            activity?.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.Buffered);
            return null;
        }

        try
        {
            // Right now, for serialization purposes every message through FanInEdge goes through the PortableMessageEnvelope state, meaning
            // we lose type information for all of them, potentially.
            (ExecutorProtocol, IGrouping<ExecutorIdentity, MessageEnvelope>)[]
                protocolGroupings = await Task.WhenAll(releasedMessages.Select(MapProtocolsAsync))
                                              .ConfigureAwait(false);

            IEnumerable<(Type? RuntimeType, MessageEnvelope MessageEnvelope)>
                typedEnvelopes = protocolGroupings.SelectMany(MapRuntimeTypes);

            Executor target = await this.RunContext.EnsureExecutorAsync(this.EdgeData.SinkId, stepTracer, cancellationToken)
                                                   .ConfigureAwait(false);

            // Materialize the filtered list via ToList() to avoid multiple enumerations
            List<MessageEnvelope> finalReleasedMessages = typedEnvelopes.Where(te => CanHandle(target, te.RuntimeType))
                                                                        .Select(te => te.MessageEnvelope)
                                                                        .ToList();
            if (finalReleasedMessages.Count == 0)
            {
                activity?.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.DroppedTypeMismatch);
                return null;
            }

            return new DeliveryMapping(finalReleasedMessages, target);

            async Task<(ExecutorProtocol, IGrouping<ExecutorIdentity, MessageEnvelope>)> MapProtocolsAsync(IGrouping<ExecutorIdentity, MessageEnvelope> grouping)
            {
                ExecutorProtocol protocol = await this.FindSourceProtocolAsync(grouping.Key.Id!, stepTracer, cancellationToken).ConfigureAwait(false);
                return (protocol, grouping);
            }

            IEnumerable<(Type?, MessageEnvelope)> MapRuntimeTypes((ExecutorProtocol, IGrouping<ExecutorIdentity, MessageEnvelope>) input)
            {
                (ExecutorProtocol protocol, IGrouping<ExecutorIdentity, MessageEnvelope> grouping) = input;
                return grouping.Select(envelope => (ResolveEnvelopeType(envelope), envelope));

                Type? ResolveEnvelopeType(MessageEnvelope messageEnvelope)
                {
                    if (messageEnvelope.Message is PortableValue portableValue)
                    {
                        return protocol.SendTypeTranslator.MapTypeId(portableValue.TypeId);
                    }

                    return messageEnvelope.Message.GetType();
                }
            }
        }
        catch (Exception) when (activity is not null)
        {
            activity.SetEdgeRunnerDeliveryStatus(EdgeRunnerDeliveryStatus.Exception);
            throw;
        }
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
