// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Options controlling the behavior of <see cref="FileSystemToolProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileSystemToolProviderOptions
{
    /// <summary>
    /// Gets or sets custom instructions provided to the agent in addition to or in place of the default
    /// instructions describing the sandboxed coding-workspace surface.
    /// </summary>
    /// <value>
    /// When <see langword="null"/>, the provider uses built-in instructions that explain the
    /// universal file-access tools and the high-fidelity coding tools side-by-side.
    /// </value>
    public string? Instructions { get; set; }

    /// <summary>
    /// Gets or sets the policy controlling sandbox limits, denylists, gitignore behavior, and ripgrep usage
    /// for the high-fidelity tools.
    /// </summary>
    /// <value>
    /// When <see langword="null"/>, a default <see cref="FileSystemPolicy"/> is used.
    /// </value>
    public FileSystemPolicy? Policy { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the file store backing the universal tools rejects
    /// paths traversing or terminating at a symbolic link.
    /// </summary>
    /// <value>
    /// <see langword="true"/> by default. Disable only when the application intentionally relies
    /// on symlinks under the root directory.
    /// </value>
    public bool RejectSymlinks { get; set; } = true;

    /// <summary>
    /// Gets or sets a list of glob patterns that block access to matching paths via the universal
    /// tools, in addition to the high-fidelity tools' own denylist defined in <see cref="Policy"/>.
    /// </summary>
    /// <value>
    /// When <see langword="null"/>, the store-level denylist defaults to <see cref="FileSystemPolicy.DefaultDenylist"/>
    /// so that secrets-like paths (e.g. <c>.env*</c>, <c>*.pem</c>) are blocked across both surfaces.
    /// </value>
    public IReadOnlyList<string>? StoreDenylist { get; set; }
}
