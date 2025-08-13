// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.Workflows.Execution;

internal record FanInEdgeState(FanInEdgeData EdgeData)
{
    private List<object>? _pendingMessages = [];

    private HashSet<string>? _unseen = new(EdgeData.SourceIds);

    public IEnumerable<object>? ProcessMessage(string sourceId, object message)
    {
        this._pendingMessages!.Add(message);
        this._unseen!.Remove(sourceId);

        if (this._unseen.Count == 0)
        {
            List<object> result = this._pendingMessages;

            this._pendingMessages = [];
            this._unseen = new(this.EdgeData.SourceIds);

            return result;
        }

        return null;
    }
}
