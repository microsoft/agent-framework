// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Represents a response handle for an actor request, providing access to the result and status updates.
/// </summary>
public sealed class ActorResponse
{
    /// <summary>
    /// Gets the identifier of the actor that is processing the request.
    /// </summary>
    [JsonPropertyName("actorId")]
    public ActorId ActorId { get; init; }

    /// <summary>
    /// Gets the unique identifier of the message/request.
    /// </summary>
    [JsonPropertyName("messageId")]
    public string? MessageId { get; init; }

    /// <summary>
    /// Gets the response data from the actor.
    /// </summary>
    [JsonPropertyName("data")]
    public JsonElement Data { get; init; }

    /// <summary>
    /// Gets or sets the current status of the request.
    /// </summary>
    [JsonPropertyName("status")]
    public RequestStatus Status { get; init; }

    /// <inheritdoc />
    public override string ToString()
    {
        string dataString;
        if (this.Data.ValueKind is JsonValueKind.Undefined)
        {
            dataString = "undefined";
        }
        else
        {
            var rawText = this.Data.GetRawText();
            dataString = rawText.Length switch
            {
                > 250 => $"{rawText.Substring(0, 250)}...",
                _ => rawText,
            };
        }

        return $"ActorResponse(ActorId: {this.ActorId}, Status: {this.Status}, MessageId: {this.MessageId ?? "null"}, Data: {dataString})";
    }
}
