// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class DeliveryMapping
{
    private readonly IEnumerable<MessageEnvelope> _envelopes;
    private readonly IEnumerable<Executor> _targets;

    public DeliveryMapping(IEnumerable<MessageEnvelope> envelopes, IEnumerable<Executor> targets)
    {
        this._envelopes = Throw.IfNull(envelopes);
        this._targets = Throw.IfNull(targets);
    }

    public DeliveryMapping(MessageEnvelope envelope, Executor target) : this([envelope], [target]) { }
    public DeliveryMapping(MessageEnvelope envelope, IEnumerable<Executor> targets) : this([envelope], targets) { }
    public DeliveryMapping(IEnumerable<MessageEnvelope> envelopes, Executor target) : this(envelopes, [target]) { }

    public IEnumerable<MessageDelivery> Deliveries => from target in this._targets
                                                      from envelope in this._envelopes
                                                      select new MessageDelivery(envelope, target);

    public void MapInto(StepContext nextStep)
    {
        foreach (Executor target in this._targets)
        {
            ConcurrentQueue<MessageEnvelope> messageQueue = nextStep.MessagesFor(target.Id);
            foreach (MessageEnvelope envelope in this._envelopes)
            {
                messageQueue.Enqueue(envelope);
            }
        }
    }
}
