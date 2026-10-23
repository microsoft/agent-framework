// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI;

/// <summary>
/// A supporting resource for a skill discovered through <c>skills/list</c>.
/// </summary>
internal sealed class AgentMcpSkillResource : AgentSkillResource
{
    private readonly ResourceContents _content;

    /// <summary>
    /// Initializes a supporting resource with verified content fetched from the MCP server.
    /// </summary>
    /// <param name="name">The resource's relative name.</param>
    /// <param name="content">The resource content that has passed size and digest verification.</param>
    /// <param name="description">An optional description of the resource.</param>
    public AgentMcpSkillResource(string name, ResourceContents content, string? description = null)
        : base(Throw.IfNullOrWhitespace(name), description)
    {
        this._content = Throw.IfNull(content);
    }

    /// <inheritdoc/>
    /// <returns>
    /// Binary content as <see cref="DataContent"/>, text as a <see cref="string"/>,
    /// or <see langword="null"/> for empty text.
    /// </returns>
    public override Task<object?> ReadAsync(IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default)
    {
        return Task.FromResult<object?>(this._content switch
        {
            TextResourceContents text => text.Text.Length == 0 ? null : text.Text,
            BlobResourceContents binary => binary.ToAIContent(),
            _ => throw new InvalidOperationException("Unsupported listed skill content."),
        });
    }
}
