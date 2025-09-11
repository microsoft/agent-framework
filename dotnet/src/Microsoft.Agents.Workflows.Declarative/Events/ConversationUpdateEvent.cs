// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Event that broadcasts the conversation identifier.
/// </summary>
public class ConversationUpdateEvent(string executorid, string conversationId) : ExecutorEvent(executorid, conversationId)
{
    /// <summary>
    /// The conversation ID associated with the workflow.
    /// </summary>
    public string ConversationId { get; } = conversationId;
}
