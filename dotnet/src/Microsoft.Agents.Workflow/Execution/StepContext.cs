// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.Workflows.Execution;

internal class StepContext
{
    public Dictionary<ExecutorIdentity, List<object>> QueuedMessages { get; } = new();

    public bool HasMessages => this.QueuedMessages.Values.Any(messageList => messageList.Count > 0);

    public List<object> MessagesFor(string? executorId)
    {
        if (!this.QueuedMessages.TryGetValue(executorId, out var messages))
        {
            messages = new List<object>();
            this.QueuedMessages[executorId] = messages;
        }

        return messages;
    }
}
