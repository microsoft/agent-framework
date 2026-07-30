// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AgentSkillResource"/> backed by content fetched from an MCP server.
/// </summary>
/// <remarks>
/// The <see cref="ReadResourceResult"/> is fetched eagerly by <see cref="AgentMcpSkill.GetResourceAsync"/>
/// at construction time; <see cref="ReadAsync"/> extracts the content from the result.
/// </remarks>
internal sealed class AgentMcpSkillResource : AgentSkillResource
{
    private readonly ReadResourceResult _result;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentMcpSkillResource"/> class with a pre-fetched result.
    /// </summary>
    /// <param name="name">The resource name (e.g. a relative path or identifier).</param>
    /// <param name="result">The result returned by the MCP server's <c>resources/read</c> request.</param>
    /// <param name="description">An optional description of the resource.</param>
    public AgentMcpSkillResource(string name, ReadResourceResult result, string? description = null)
        : base(Throw.IfNullOrWhitespace(name), description)
    {
        this._result = Throw.IfNull(result);
    }

    /// <inheritdoc/>
    /// <returns>
    /// A <see cref="DataContent"/> when the resource contains binary content, a <see cref="string"/> when
    /// it contains text, or <see langword="null"/> when the server returned no content blocks.
    /// </returns>
    public override Task<object?> ReadAsync(IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default)
    {
        BlobResourceContents? blob = this._result.Contents.OfType<BlobResourceContents>().FirstOrDefault();
        if (blob is not null)
        {
            return Task.FromResult<object?>(blob.ToAIContent());
        }

        string text = string.Join("\n", this._result.Contents.OfType<TextResourceContents>().Select(c => c.Text));

        if (text.Length == 0)
        {
            return Task.FromResult<object?>(null);
        }

        return Task.FromResult<object?>(text);
    }
}
