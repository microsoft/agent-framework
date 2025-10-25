// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;

/// <summary>
/// Response containing created conversation items.
/// </summary>
internal sealed class CreateItemsResponse
{
    /// <summary>
    /// The list of created items.
    /// </summary>
    [JsonPropertyName("data")]
    public required List<ConversationItem> Data { get; init; }
}
