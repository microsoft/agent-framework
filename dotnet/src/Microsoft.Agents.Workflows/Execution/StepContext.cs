// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;

namespace Microsoft.Agents.Workflows.Execution;

internal class StepContext
{
    public Dictionary<ExecutorIdentity, List<MessageEnvelope>> QueuedMessages { get; } = new();

    public bool HasMessages => this.QueuedMessages.Values.Any(messageList => messageList.Count > 0);

    public List<MessageEnvelope> MessagesFor(string? executorId)
    {
        if (!this.QueuedMessages.TryGetValue(executorId, out var messages))
        {
            this.QueuedMessages[executorId] = messages = new();
        }

        return messages;
    }
}
