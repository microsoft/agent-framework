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

    /// <summary>
    /// Is the conversation associated with the workflow.
    /// </summary>
    public bool IsWorkflow { get; internal init; }

    /// <summary>
    /// Initializes a new instance of <see cref="ConversationUpdateEvent"/>.
    /// </summary>
    /// <param name="conversationId">The identifier of the associated conversation.</param>
    public ConversationUpdateEvent(string conversationId)
        : base(conversationId)
    {
        this.ConversationId = conversationId;
    }
}
