// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Immutable;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Durable agent state content representing a function call.
/// </summary>
internal sealed class DurableAgentStateFunctionCallContent : DurableAgentStateContent
{
    /// <summary>
    /// The function call arguments.
    /// </summary>
    /// TODO: Consider ensuring that empty dictionaries are omitted from serialization.
    [JsonPropertyName("arguments")]
    public required IReadOnlyDictionary<string, object?> Arguments { get; init; } =
        ImmutableDictionary<string, object?>.Empty;

    /// <summary>
    /// Gets the function call identifier.
    /// </summary>
    /// <remarks>
    /// This is used to correlate this function call with its resulting
    /// <see cref="DurableAgentStateFunctionResultContent"/>.
    /// </remarks>
    [JsonPropertyName("callId")]
    public required string CallId { get; init; }

    /// <summary>
    /// Gets the function name.
    /// </summary>
    [JsonPropertyName("name")]
    public required string Name { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateFunctionCallContent"/> from a <see cref="FunctionCallContent"/>.
    /// </summary>
    /// <param name="content">The <see cref="FunctionCallContent"/> to convert.</param>
    /// <returns>
    /// A <see cref="DurableAgentStateFunctionCallContent"/> representing the original content.
    /// </returns>
    public static DurableAgentStateFunctionCallContent FromFunctionCallContent(FunctionCallContent content)
    {
        return new DurableAgentStateFunctionCallContent()
        {
            Arguments = content.Arguments?.ToImmutableDictionary() ?? ImmutableDictionary<string, object?>.Empty,
            CallId = content.CallId,
            Name = content.Name
        };
    }

    /// <inheritdoc/>
    public override AIContent ToAIContent()
    {
        return new FunctionCallContent(
            this.CallId,
            this.Name,
            new Dictionary<string, object?>(this.Arguments));
    }
}
