// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.Workflows.Checkpointing;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class StepContext
{
    public Dictionary<ExecutorIdentity, List<MessageEnvelope>> QueuedMessages { get; } = [];

    public bool HasMessages => this.QueuedMessages.Values.Any(messageList => messageList.Count > 0);

    public List<MessageEnvelope> MessagesFor(string? executorId)
    {
        if (!this.QueuedMessages.TryGetValue(executorId, out var messages))
        {
            this.QueuedMessages[executorId] = messages = [];
        }

        return messages;
    }

    // TODO: Create a MessageEnvelope class that extends from the ExportedState object (with appropriate rename) to avoid
    // unnecessary wrapping and unwrapping of messages during checkpointing.
    internal Dictionary<ExecutorIdentity, List<PortableMessageEnvelope>> ExportMessages()
    {
        return this.QueuedMessages.Keys.ToDictionary(
            keySelector: identity => identity,
            elementSelector: identity => this.QueuedMessages[identity]
                                             .ConvertAll(v => new PortableMessageEnvelope(v))
        );
    }

    internal void ImportMessages(Dictionary<ExecutorIdentity, List<PortableMessageEnvelope>> messages)
    {
        foreach (ExecutorIdentity identity in messages.Keys)
        {
            this.QueuedMessages[identity] = messages[identity].ConvertAll(UnwrapExportedState);
        }

        static MessageEnvelope UnwrapExportedState(PortableMessageEnvelope es) => es.ToMessageEnvelope();
    }
}
