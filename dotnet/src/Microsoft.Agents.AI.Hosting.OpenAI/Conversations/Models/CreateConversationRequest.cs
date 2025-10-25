// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;

/// <summary>
/// Request to create a new conversation.
/// </summary>
internal sealed record CreateConversationRequest
{
    /// <summary>
    /// Initial items to include in the conversation context. You may add up to 20 items at a time.
    /// </summary>
    [JsonPropertyName("items")]
    [SuppressMessage("Performance", "CA1819:Properties should not return arrays", Justification = "Matches OpenAI API specification")]
    public ConversationItem[]? Items { get; init; }

    /// <summary>
    /// Set of 16 key-value pairs that can be attached to a conversation.
    /// </summary>
    [JsonPropertyName("metadata")]
    public Dictionary<string, string>? Metadata { get; init; }
}
