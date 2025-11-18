// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents durable agent state content that contains hosted vector store content.
/// </summary>
internal sealed class DurableAgentStateHostedVectorStoreContent : DurableAgentStateContent
{
    /// <summary>
    /// Gets the vector store ID of the hosted vector store content.
    /// </summary>
    [JsonPropertyName("vectorStoreId")]
    public required string VectorStoreId { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateHostedVectorStoreContent"/> from a <see cref="HostedVectorStoreContent"/>.
    /// </summary>
    /// <param name="content">The <see cref="HostedVectorStoreContent"/> to convert.</param>
    /// <returns>
    /// A <see cref="DurableAgentStateHostedVectorStoreContent"/> representing the original <see cref="HostedVectorStoreContent"/>.
    /// </returns>
    public static DurableAgentStateHostedVectorStoreContent FromHostedVectorStoreContent(HostedVectorStoreContent content)
    {
        return new DurableAgentStateHostedVectorStoreContent()
        {
            VectorStoreId = content.VectorStoreId
        };
    }

    /// <inheritdoc/>
    public override AIContent ToAIContent()
    {
        return new HostedVectorStoreContent(this.VectorStoreId);
    }
}
