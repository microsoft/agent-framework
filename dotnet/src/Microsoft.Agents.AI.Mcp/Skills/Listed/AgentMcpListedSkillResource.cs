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
/// A supporting resource for a skill discovered through <c>skills/list</c>.
/// </summary>
internal sealed class AgentMcpListedSkillResource : AgentSkillResource
{
    private readonly ReadResourceResult _result;

    /// <summary>
    /// Initializes a supporting resource with content fetched from the MCP server.
    /// </summary>
    /// <param name="name">The resource's relative name.</param>
    /// <param name="result">The resource content returned by the MCP server.</param>
    /// <param name="description">An optional description of the resource.</param>
    public AgentMcpListedSkillResource(string name, ReadResourceResult result, string? description = null)
        : base(Throw.IfNullOrWhitespace(name), description)
    {
        this._result = Throw.IfNull(result);
    }

    /// <inheritdoc/>
    /// <returns>
    /// Binary content as <see cref="DataContent"/>, text as a <see cref="string"/>,
    /// or <see langword="null"/> when neither is available.
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
