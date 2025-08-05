// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.Workflows.Core;

namespace Microsoft.Agents.Workflows.Execution;

internal record FanInEdgeState(FanInEdgeData EdgeData)
{
    private List<object>? _pendingMessages
        = EdgeData.Trigger == FanInTrigger.WhenAll ? [] : null;

    private HashSet<string>? _unseen
        = EdgeData.Trigger == FanInTrigger.WhenAll ? new(EdgeData.SourceIds) : null;

    public IEnumerable<object>? ProcessMessage(string sourceId, object message)
    {
        if (this.EdgeData.Trigger == FanInTrigger.WhenAll)
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

        return [message];
    }
}
