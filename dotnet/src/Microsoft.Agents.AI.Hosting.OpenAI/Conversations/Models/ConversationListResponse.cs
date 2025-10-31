// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;

/// <summary>
/// Response containing a list of conversations.
/// </summary>
internal sealed class ConversationListResponse
{
    /// <summary>
    /// The object type, always "list".
    /// </summary>
    [JsonPropertyName("object")]
    [SuppressMessage("Naming", "CA1720:Identifiers should not match keywords", Justification = "Matches OpenAI API specification")]
    public string Object => "list";

    /// <summary>
    /// The list of conversations.
    /// </summary>
    [JsonPropertyName("data")]
    public required List<Conversation> Data { get; init; }

    /// <summary>
    /// Whether there are more items available.
    /// </summary>
    [JsonPropertyName("has_more")]
    public required bool HasMore { get; init; }
}
