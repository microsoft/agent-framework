// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A file-path-backed skill resource. Reads content from a file on disk relative to the skill directory.
/// </summary>
internal sealed class AgentFileSkillResource : AgentSkillResource
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFileSkillResource"/> class.
    /// </summary>
    /// <param name="name">The resource name (relative path within the skill directory).</param>
    /// <param name="fullPath">The absolute file path to the resource.</param>
    public AgentFileSkillResource(string name, string fullPath)
        : base(name)
    {
        this.FullPath = Throw.IfNullOrWhitespace(fullPath);
    }

    /// <summary>
    /// Gets the absolute file path to the resource.
    /// </summary>
    public string FullPath { get; }

    /// <inheritdoc/>
    public override async Task<object?> ReadAsync(IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default)
    {
#if NET8_0_OR_GREATER
        return await File.ReadAllTextAsync(this.FullPath, Encoding.UTF8, cancellationToken).ConfigureAwait(false);
#else
        using var reader = new StreamReader(this.FullPath, Encoding.UTF8);
        return await reader.ReadToEndAsync().ConfigureAwait(false);
#endif
    }
}
