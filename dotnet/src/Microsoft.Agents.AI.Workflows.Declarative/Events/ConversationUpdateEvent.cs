// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Event that broadcasts the conversation identifier.
/// </summary>
public sealed class ConversationUpdateEvent : WorkflowEvent
{
    /// <summary>
    /// The conversation ID associated with the workflow.
    /// </summary>
    public string ConversationId { get; }

    internal ConversationUpdateEvent(string conversationId)
        : base(conversationId)
    {
        this.ConversationId = conversationId;
    }
}
