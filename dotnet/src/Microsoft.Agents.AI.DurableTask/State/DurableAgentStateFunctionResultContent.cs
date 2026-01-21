// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
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
    /// Gets the function result as a JSON element.
    /// </summary>
    /// <remarks>
    /// The result is stored as a <see cref="JsonElement"/> to support serialization
    /// of arbitrary types, including <see cref="AIContent"/> types returned by MCP tools.
    /// </remarks>
    [JsonPropertyName("result")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? Result { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateFunctionResultContent"/> from a <see cref="FunctionResultContent"/>.
    /// </summary>
    /// <param name="content">The <see cref="FunctionResultContent"/> to convert.</param>
    /// <returns>A <see cref="DurableAgentStateFunctionResultContent"/> representing the original content.</returns>
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "DurableAgentJsonUtilities.DefaultOptions chains AIJsonUtilities which has metadata for AIContent types.")]
    [UnconditionalSuppressMessage("ReflectionAnalysis", "IL3050", Justification = "DurableAgentJsonUtilities.DefaultOptions chains AIJsonUtilities which has metadata for AIContent types.")]
    public static DurableAgentStateFunctionResultContent FromFunctionResultContent(FunctionResultContent content)
    {
        JsonElement? resultElement = null;
        if (content.Result is not null)
        {
            // Use DurableAgentJsonUtilities.DefaultOptions which chains AIJsonUtilities
            // to properly serialize AIContent types (e.g., TextContent from MCP tools).
            resultElement = JsonSerializer.SerializeToElement(
                content.Result,
                DurableAgentJsonUtilities.DefaultOptions);
        }

        return new DurableAgentStateFunctionResultContent()
        {
            CallId = content.CallId,
            Result = resultElement
        };
    }

    /// <inheritdoc/>
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "DurableAgentJsonUtilities.DefaultOptions chains AIJsonUtilities which has metadata for AIContent types.")]
    [UnconditionalSuppressMessage("ReflectionAnalysis", "IL3050", Justification = "DurableAgentJsonUtilities.DefaultOptions chains AIJsonUtilities which has metadata for AIContent types.")]
    public override AIContent ToAIContent()
    {
        object? result = null;
        if (this.Result.HasValue)
        {
            // Deserialize back using the same options to preserve type information
            result = this.Result.Value.Deserialize<object?>(DurableAgentJsonUtilities.DefaultOptions);
        }

        return new FunctionResultContent(this.CallId, result);
    }
}
