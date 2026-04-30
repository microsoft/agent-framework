// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options controlling the behavior of <see cref="FileSystemAgentFileStore"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileSystemAgentFileStoreOptions
{
    /// <summary>
    /// Gets or sets a value indicating whether the store rejects paths that traverse
    /// or terminate at a symbolic link / reparse point.
    /// </summary>
    /// <value>
    /// <see langword="true"/> by default. Disable only when the application intentionally relies
    /// on symlinks under the root directory.
    /// </value>
    public bool RejectSymlinks { get; set; } = true;

    /// <summary>
    /// Gets or sets a list of glob patterns that block access to matching paths even if they
    /// resolve to a safe location under the root.
    /// </summary>
    /// <value>
    /// An empty list by default. A recommended set of secrets-protecting patterns is available
    /// via <see cref="FileSystemPolicy.DefaultDenylist"/>.
    /// </value>
    public IReadOnlyList<string> Denylist { get; set; } = [];
}
