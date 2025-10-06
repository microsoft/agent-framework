// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Checkpointing;

namespace Microsoft.Agents.AI.Workflows.Execution;

internal sealed class StepContext
{
    public ConcurrentDictionary<string, ConcurrentQueue<MessageEnvelope>> QueuedMessages { get; } = [];

    public bool HasMessages => this.QueuedMessages.Values.Any(messageQueue => !messageQueue.IsEmpty);

    public ConcurrentQueue<MessageEnvelope> MessagesFor(string target)
    {
        return this.QueuedMessages.GetOrAdd(target, _ => new ConcurrentQueue<MessageEnvelope>());
    }

    // TODO: Create a MessageEnvelope class that extends from the ExportedState object (with appropriate rename) to avoid
    // unnecessary wrapping and unwrapping of messages during checkpointing.
    internal Dictionary<string, List<PortableMessageEnvelope>> ExportMessages()
    {
        return this.QueuedMessages.Keys.ToDictionary(
            keySelector: identity => identity,
            elementSelector: identity => this.QueuedMessages[identity]
                                             .Select(v => new PortableMessageEnvelope(v))
                                             .ToList()
        );
    }

    internal void ImportMessages(Dictionary<string, List<PortableMessageEnvelope>> messages)
    {
        foreach (string identity in messages.Keys)
        {
            this.QueuedMessages[identity] = new(messages[identity].Select(UnwrapExportedState));
        }

        static MessageEnvelope UnwrapExportedState(PortableMessageEnvelope es) => es.ToMessageEnvelope();
    }
}
