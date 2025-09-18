// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using System.Threading;
using Microsoft.Agents.Workflows.Checkpointing;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class FanInEdgeState
{
    private List<PortableMessageEnvelope> _pendingMessages;
    public FanInEdgeState(FanInEdgeData fanInEdge)
    {
        this.SourceIds = fanInEdge.SourceIds.ToArray();
        this.Unseen = new(this.SourceIds);

        this._pendingMessages = [];
    }

    public string[] SourceIds { get; }
    public HashSet<string> Unseen { get; private set; }
    public List<PortableMessageEnvelope> PendingMessages => this._pendingMessages;

    [JsonConstructor]
    public FanInEdgeState(string[] sourceIds, HashSet<string> unseen, List<PortableMessageEnvelope> pendingMessages)
    {
        this.SourceIds = sourceIds;
        this.Unseen = unseen;

        this._pendingMessages = pendingMessages;
    }

    public IEnumerable<MessageEnvelope>? ProcessMessage(string sourceId, MessageEnvelope envelope)
    {
        this.PendingMessages.Add(new(envelope));
        this.Unseen.Remove(sourceId);

        if (this.Unseen.Count == 0)
        {
            List<PortableMessageEnvelope> takenMessages = Interlocked.Exchange(ref this._pendingMessages, []);
            this.Unseen = new(this.SourceIds);

            if (takenMessages.Count == 0)
            {
                return null;
            }

            return takenMessages.Select(portable => portable.ToMessageEnvelope());
        }

        return null;
    }
}
