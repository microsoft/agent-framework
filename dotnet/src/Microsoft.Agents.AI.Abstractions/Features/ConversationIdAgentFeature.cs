// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// An agent feature that allows providing a conversation identifier.
/// </summary>
/// <remarks>
/// This feature allows a user to provide a specific identifier for chat history when stored in the underlying AI service.
/// </remarks>
public class ConversationIdAgentFeature
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ConversationIdAgentFeature"/> class with the specified thread
    /// identifier.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the thread required by the underlying AI service. Cannot be <see langword="null"/> or empty.</param>
    public ConversationIdAgentFeature(string conversationId)
    {
        this.ConversationId = Throw.IfNullOrWhitespace(conversationId);
    }

    /// <summary>
    /// Gets the conversation identifier.
    /// </summary>
    public string ConversationId { get; }
}
