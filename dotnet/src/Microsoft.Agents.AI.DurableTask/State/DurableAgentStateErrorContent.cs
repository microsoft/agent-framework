// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents durable agent state content that contains error content.
/// </summary>
internal sealed class DurableAgentStateErrorContent : DurableAgentStateContent
{
    /// <summary>
    /// Gets the error message.
    /// </summary>
    [JsonPropertyName("message")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Message { get; init; }

    /// <summary>
    /// Gets the error code.
    /// </summary>
    [JsonPropertyName("errorCode")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ErrorCode { get; init; }

    /// <summary>
    /// Gets the error details.
    /// </summary>
    [JsonPropertyName("details")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Details { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateErrorContent"/> from an <see cref="ErrorContent"/>.
    /// </summary>
    /// <param name="content">The <see cref="ErrorContent"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateErrorContent"/> representing the original
    /// <see cref="ErrorContent"/>.</returns>
    public static DurableAgentStateErrorContent FromErrorContent(ErrorContent content)
    {
        return new DurableAgentStateErrorContent()
        {
            Details = content.Details,
            ErrorCode = content.ErrorCode,
            Message = content.Message
        };
    }

    /// <inheritdoc/>
    public override AIContent ToAIContent()
    {
        return new ErrorContent(this.Message)
        {
            Details = this.Details,
            ErrorCode = this.ErrorCode
        };
    }
}
