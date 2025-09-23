// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents;

/// <summary>Provides metadata about an <see cref="AgentThread"/>.</summary>
public class AgentThreadMetadata
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentThreadMetadata"/> class.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation, if available.</param>
    public AgentThreadMetadata(string? conversationId)
    {
        ConversationId = conversationId;
    }

    /// <summary>
    /// Gets the unique identifier for the conversation, if available.
    /// </summary>
    /// <remarks>
    /// The meaning of this ID may vary depending on the agent implementation.
    /// </remarks>
    public string? ConversationId { get; }
}
