// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents a single message within a durable agent state entry.
/// </summary>
internal sealed class DurableAgentStateMessage
{
    /// <summary>
    /// Gets the name of the author of this message.
    /// </summary>
    [JsonPropertyName("authorName")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? AuthorName { get; init; }

    /// <summary>
    /// Gets the timestamp when this message was created.
    /// </summary>
    [JsonPropertyName("createdAt")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public DateTimeOffset? CreatedAt { get; init; }

    /// <summary>
    /// Gets the contents of this message.
    /// </summary>
    [JsonPropertyName("contents")]
    public IReadOnlyList<DurableAgentStateContent> Contents { get; init; } = [];

    /// <summary>
    /// Gets the role of the message sender (e.g., "user", "assistant", "system").
    /// </summary>
    [JsonPropertyName("role")]
    public required string Role { get; init; }

    /// <summary>
    /// Gets any additional data found during deserialization that does not map to known properties.
    /// </summary>
    [JsonExtensionData]
    public IDictionary<string, JsonElement>? ExtensionData { get; set; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateMessage"/> from a <see cref="ChatMessage"/>.
    /// </summary>
    /// <param name="message">The <see cref="ChatMessage"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateMessage"/> representing the original message.</returns>
    public static DurableAgentStateMessage FromChatMessage(ChatMessage message)
    {
        return new DurableAgentStateMessage()
        {
            CreatedAt = message.CreatedAt,
            AuthorName = message.AuthorName,
            Role = message.Role.ToString(),
            Contents = message.Contents.Select(DurableAgentStateContent.FromAIContent).ToList()
        };
    }

    /// <summary>
    /// Converts this <see cref="DurableAgentStateMessage"/> to a <see cref="ChatMessage"/>.
    /// </summary>
    /// <returns>A <see cref="ChatMessage"/> representing this message.</returns>
    public ChatMessage ToChatMessage()
    {
        return new ChatMessage()
        {
            CreatedAt = this.CreatedAt,
            AuthorName = this.AuthorName,
            Contents = this.Contents.Select(c => c.ToAIContent()).ToList(),
            Role = new(this.Role)
        };
    }
}
