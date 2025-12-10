// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents the function result content for a durable agent state response.
/// </summary>
internal sealed class DurableAgentStateFunctionResultContent : DurableAgentStateContent
{
    /// <summary>
    /// Gets the function call identifier.
    /// </summary>
    /// <remarks>
    /// This is used to correlate this function result with its originating
    /// <see cref="DurableAgentStateFunctionCallContent"/>.
    /// </remarks>
    [JsonPropertyName("callId")]
    public required string CallId { get; init; }

    /// <summary>
    /// Gets the function result.
    /// </summary>
    [JsonPropertyName("result")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public object? Result { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateFunctionResultContent"/> from a <see cref="FunctionResultContent"/>.
    /// </summary>
    /// <param name="content">The <see cref="FunctionResultContent"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateFunctionResultContent"/> representing the original content.</returns>
    public static DurableAgentStateFunctionResultContent FromFunctionResultContent(FunctionResultContent content)
    {
        return new DurableAgentStateFunctionResultContent()
        {
            CallId = content.CallId,
            Result = content.Result
        };
    }

    /// <inheritdoc/>
    public override AIContent ToAIContent()
    {
        return new FunctionResultContent(this.CallId, this.Result);
    }
}
