// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hosting.Channels;

/// <summary>
/// File-system layout for <see cref="FileHostStateStore"/>. All paths optional; per-component paths
/// derive from <see cref="Root"/> when unset. v1 owns only reset-session aliases and workflow checkpoint
/// path derivation.
/// </summary>
public sealed class HostStatePathOptions
{
    /// <summary>Gets or sets the root directory under which per-component subpaths are derived.</summary>
    public string? Root { get; set; }

    /// <summary>Gets or sets the path for reset-session aliases.</summary>
    public string? AliasesPath { get; set; }

    /// <summary>Gets or sets the root path for per-isolation-key workflow checkpoint derivation.</summary>
    public string? CheckpointsPath { get; set; }
}
