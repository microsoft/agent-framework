// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;

/// <summary>
/// Represents a conversation in the system.
/// </summary>
internal sealed record Conversation
{
    /// <summary>
    /// The unique identifier for the conversation.
    /// </summary>
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    /// <summary>
    /// The object type, always "conversation".
    /// </summary>
    [JsonPropertyName("object")]
    [SuppressMessage("Naming", "CA1720:Identifiers should not match keywords", Justification = "Matches OpenAI API specification")]
    public string Object => "conversation";

    /// <summary>
    /// The Unix timestamp (in seconds) for when the conversation was created.
    /// </summary>
    [JsonPropertyName("created_at")]
    public required long CreatedAt { get; init; }

    /// <summary>
    /// Set of 16 key-value pairs that can be attached to a conversation.
    /// </summary>
    [JsonPropertyName("metadata")]
    public Dictionary<string, string> Metadata { get; init; } = [];
}
