// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.Workflows.Checkpointing;

namespace Microsoft.Agents.Workflows.Execution;

internal sealed class StepContext
{
    public Dictionary<string, List<MessageEnvelope>> QueuedMessages { get; } = [];

    public bool HasMessages => this.QueuedMessages.Values.Any(messageList => messageList.Count > 0);

    public List<MessageEnvelope> MessagesFor(string target)
    {
        if (!this.QueuedMessages.TryGetValue(target, out var messages))
        {
            this.QueuedMessages[target] = messages = [];
        }

        return messages;
    }

    // TODO: Create a MessageEnvelope class that extends from the ExportedState object (with appropriate rename) to avoid
    // unnecessary wrapping and unwrapping of messages during checkpointing.
    internal Dictionary<string, List<PortableMessageEnvelope>> ExportMessages()
    {
        return this.QueuedMessages.Keys.ToDictionary(
            keySelector: identity => identity,
            elementSelector: identity => this.QueuedMessages[identity]
                                             .ConvertAll(v => new PortableMessageEnvelope(v))
        );
    }

    internal void ImportMessages(Dictionary<string, List<PortableMessageEnvelope>> messages)
    {
        foreach (string identity in messages.Keys)
        {
            this.QueuedMessages[identity] = messages[identity].ConvertAll(UnwrapExportedState);
        }

        static MessageEnvelope UnwrapExportedState(PortableMessageEnvelope es) => es.ToMessageEnvelope();
    }
}
