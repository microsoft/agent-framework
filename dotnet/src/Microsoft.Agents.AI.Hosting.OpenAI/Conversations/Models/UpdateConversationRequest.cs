// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Conversations.Models;

/// <summary>
/// Request to update an existing conversation.
/// </summary>
internal sealed class UpdateConversationRequest
{
    /// <summary>
    /// Set of 16 key-value pairs that can be attached to a conversation.
    /// </summary>
    [JsonPropertyName("metadata")]
    public required Dictionary<string, string> Metadata { get; init; }
}
