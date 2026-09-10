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
    private readonly AgentFileSkillPathScope _scope;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFileSkillResource"/> class.
    /// </summary>
    /// <param name="name">The resource name (relative path within the skill directory).</param>
    /// <param name="fullPath">The absolute file path to the resource.</param>
    /// <param name="scope">The trusted path scope the resource was discovered in.</param>
    public AgentFileSkillResource(string name, string fullPath, AgentFileSkillPathScope scope)
        : base(name)
    {
        this.FullPath = Throw.IfNullOrWhitespace(fullPath);
        this._scope = Throw.IfNull(scope);
    }

    /// <summary>
    /// Gets the absolute file path to the resource.
    /// </summary>
    public string FullPath { get; }

    /// <inheritdoc/>
    public override async Task<object?> ReadAsync(IServiceProvider? serviceProvider = null, CancellationToken cancellationToken = default)
    {
        string validatedPath = AgentFileSkillPathValidator.ValidateForUse(this.FullPath, this._scope, "Resource", this.Name);

#if NET8_0_OR_GREATER
        return await File.ReadAllTextAsync(validatedPath, Encoding.UTF8, cancellationToken).ConfigureAwait(false);
#else
        using var reader = new StreamReader(validatedPath, Encoding.UTF8);
        return await reader.ReadToEndAsync().ConfigureAwait(false);
#endif
    }
}
