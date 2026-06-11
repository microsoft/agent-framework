// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class FanInEdgeState
{
    private readonly object _syncLock = new();

    public FanInEdgeState(FanInEdgeData fanInEdge)
    {
        this.SourceIds = fanInEdge.SourceIds.ToArray();
        this.Unseen = [.. this.SourceIds];

        this.PendingMessages = [];
    }

    public string[] SourceIds { get; }
    public HashSet<string> Unseen { get; private set; }
    public List<PortableMessageEnvelope> PendingMessages { get; private set; }

    [JsonConstructor]
    public FanInEdgeState(string[] sourceIds, HashSet<string> unseen, List<PortableMessageEnvelope> pendingMessages)
    {
        this.SourceIds = sourceIds;
        this.Unseen = unseen;

        this.PendingMessages = pendingMessages;
    }

    public IEnumerable<IGrouping<ExecutorIdentity, MessageEnvelope>>? ProcessMessage(string sourceId, MessageEnvelope envelope)
    {
        List<PortableMessageEnvelope>? takenMessages = null;

        // Serialize concurrent calls from parallel executor tasks during superstep execution.
        // NOTE - IMPORTANT: If this ProcessMessage method ever becomes async, replace this lock with an async friendly solution to avoid deadlocks.
        lock (this._syncLock)
        {
            this.PendingMessages.Add(new(envelope));
            this.Unseen.Remove(sourceId);

            if (this.Unseen.Count == 0)
            {
                takenMessages = this.PendingMessages;
                this.PendingMessages = [];
                this.Unseen = [.. this.SourceIds];
            }
        }

        if (takenMessages is null || takenMessages.Count == 0)
        {
            return null;
        }

        return takenMessages
            .Select(portable => portable.ToMessageEnvelope())
            .GroupBy(messageEnvelope => messageEnvelope.Source);
    }
}
