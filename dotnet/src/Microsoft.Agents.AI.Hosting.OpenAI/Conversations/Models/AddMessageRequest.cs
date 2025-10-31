// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;

/// <summary>
/// Request to create items in a conversation.
/// </summary>
internal sealed record CreateItemsRequest
{
    /// <summary>
    /// The items to add to the conversation. You may add up to 20 items at a time.
    /// </summary>
    [JsonPropertyName("items")]
    [SuppressMessage("Performance", "CA1819:Properties should not return arrays", Justification = "Matches OpenAI API specification")]
    public required ConversationItem[] Items { get; init; }
}
