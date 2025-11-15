// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// Represents durable agent state content that contains hosted file content.
/// </summary>
internal sealed class DurableAgentStateHostedFileContent : DurableAgentStateContent
{
    /// <summary>
    /// Gets the file ID of the hosted file content.
    /// </summary>
    [JsonPropertyName("fileId")]
    public required string FileId { get; init; }

    /// <summary>
    /// Creates a <see cref="DurableAgentStateHostedFileContent"/> from a <see cref="HostedFileContent"/>.
    /// </summary>
    /// <param name="content">The <see cref="HostedFileContent"/> to convert.</param>
    /// <returns>
    /// A <see cref="DurableAgentStateHostedFileContent"/> representing the original <see cref="HostedFileContent"/>.
    /// </returns>
    public static DurableAgentStateHostedFileContent FromHostedFileContent(HostedFileContent content)
    {
        return new DurableAgentStateHostedFileContent()
        {
            FileId = content.FileId
        };
    }

    /// <inheritdoc/>
    public override AIContent ToAIContent()
    {
        return new HostedFileContent(this.FileId);
    }
}
