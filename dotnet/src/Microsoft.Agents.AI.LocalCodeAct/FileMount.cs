// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// Defines a file or directory mounted into the code execution environment.
/// </summary>
/// <remarks>
/// Mounts expose host paths directly to code running in a subprocess. The MountPath
/// parameter is metadata only; code accesses the HostPath directly. Real isolation
/// must come from external container/VM sandboxing.
/// </remarks>
public sealed record FileMount
{
    /// <summary>
    /// Gets or sets the path on the host filesystem to expose to the subprocess.
    /// </summary>
    public required string HostPath { get; init; }

    /// <summary>
    /// Gets or sets the logical path name for documentation. Not enforced at runtime.
    /// </summary>
    public required string MountPath { get; init; }

    /// <summary>
    /// Gets or sets the access mode for the mount. Default is ReadWrite.
    /// </summary>
    public FileMountMode Mode { get; init; } = FileMountMode.ReadWrite;

    /// <summary>
    /// Gets or sets the maximum bytes that can be written to a single file in this mount (read-write only).
    /// If null, uses the tool's MaxFileBytesPerFile limit.
    /// </summary>
    public int? WriteBytesLimit { get; init; }
}

/// <summary>
/// File mount access mode.
/// </summary>
public enum FileMountMode
{
    /// <summary>
    /// Read-only access. Files cannot be created or modified.
    /// </summary>
    ReadOnly,

    /// <summary>
    /// Read-write access. Files can be created and modified.
    /// Output files are captured and returned as data content.
    /// </summary>
    ReadWrite,
}
