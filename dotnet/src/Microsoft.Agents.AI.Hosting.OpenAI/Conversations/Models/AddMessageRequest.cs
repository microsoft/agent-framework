// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;

/// <summary>
/// Request to create items in a conversation.
/// </summary>
internal sealed class CreateItemsRequest
{
    /// <summary>
    /// The items to add to the conversation. You may add up to 20 items at a time.
    /// Items should be ItemParam objects (messages without IDs, function call outputs, etc.).
    /// The server will assign IDs when creating the items.
    /// </summary>
    [JsonPropertyName("items")]
    public required List<ItemParam> Items { get; init; }
}
