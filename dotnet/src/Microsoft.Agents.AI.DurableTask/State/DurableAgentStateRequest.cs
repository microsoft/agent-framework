// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents a user or system request entry in the durable agent state.
/// </summary>
internal sealed class DurableAgentStateRequest : DurableAgentStateEntry
{
    /// <summary>
    /// Gets the expected response type for this request (e.g. "json" or "text").
    /// </summary>
    /// <remarks>
    /// If omitted, the expectation is that the agent will respond in plain text.
    /// </remarks>
    [JsonPropertyName("responseType")]
    public string? ResponseType { get; init; }

    /// <summary>
    /// Gets the expected response JSON schema for this request, if applicable.
    /// </summary>
    /// <remarks>
    /// This is only applicable when <see cref="ResponseType"/> is "json".
    /// If omitted, no specific schema is expected.
    /// </remarks>
    [JsonPropertyName("responseSchema")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? ResponseSchema { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateRequest"/> from a <see cref="RunRequest"/>.
    /// </summary>
    /// <param name="request">The <see cref="RunRequest"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateRequest"/> representing the original request.</returns>
    public static DurableAgentStateRequest FromRunRequest(RunRequest request)
    {
        return new DurableAgentStateRequest()
        {
            CorrelationId = request.CorrelationId,
            Messages = request.Messages.Select(DurableAgentStateMessage.FromChatMessage).ToList(),
            CreatedAt = request.Messages.Min(m => m.CreatedAt) ?? DateTimeOffset.UtcNow,
            ResponseType = request.ResponseFormat is ChatResponseFormatJson ? "json" : "text",
            ResponseSchema = (request.ResponseFormat as ChatResponseFormatJson)?.Schema
        };
    }
}
