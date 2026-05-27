// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// File mount access mode.
/// </summary>
public enum FileMountMode
{
    /// <summary>Read-only access. Files are not scanned for capture after execution.</summary>
    ReadOnly,

    /// <summary>Read-write access. New or modified files are captured after execution.</summary>
    ReadWrite,
}

/// <summary>
/// Represents a host directory exposed to locally executed code.
/// </summary>
/// <remarks>
/// <para>
/// Unlike a true sandbox, mounts in this package expose <see cref="HostPath"/>
/// directly to the subprocess. The <see cref="MountPath"/> is metadata used to
/// describe the mount to the model in the function description and to label
/// captured files. Real isolation must come from the surrounding sandbox
/// (container, VM, Foundry hosted agent, etc.).
/// </para>
/// </remarks>
public sealed class FileMount
{
    /// <summary>
    /// Initializes a new instance of the <see cref="FileMount"/> class.
    /// </summary>
    /// <param name="hostPath">Path on the host filesystem to expose to the subprocess. Must exist.</param>
    /// <param name="mountPath">
    /// Logical path used to describe the mount to the model (for example <c>"/input/data.csv"</c>).
    /// </param>
    /// <param name="mode">Access mode for the mount. Defaults to <see cref="FileMountMode.ReadWrite"/>.</param>
    /// <param name="writeBytesLimit">
    /// Optional per-mount write capture limit (in bytes). When <see langword="null"/>, the global
    /// <see cref="ProcessExecutionLimits.MaxCapturedFileBytes"/> applies.
    /// </param>
    public FileMount(string hostPath, string mountPath, FileMountMode mode = FileMountMode.ReadWrite, long? writeBytesLimit = null)
    {
        Microsoft.Shared.Diagnostics.Throw.IfNull(hostPath);
        Microsoft.Shared.Diagnostics.Throw.IfNull(mountPath);
        if (string.IsNullOrWhiteSpace(hostPath))
        {
            throw new System.ArgumentException("Host path must not be empty.", nameof(hostPath));
        }

        if (string.IsNullOrWhiteSpace(mountPath))
        {
            throw new System.ArgumentException("Mount path must not be empty.", nameof(mountPath));
        }

        this.HostPath = hostPath;
        this.MountPath = mountPath;
        this.Mode = mode;
        this.WriteBytesLimit = writeBytesLimit;
    }

    /// <summary>Gets the host filesystem path exposed to the subprocess.</summary>
    public string HostPath { get; }

    /// <summary>Gets the logical mount path used to describe the mount to the model.</summary>
    public string MountPath { get; }

    /// <summary>Gets the access mode for the mount.</summary>
    public FileMountMode Mode { get; }

    /// <summary>Gets the optional per-mount write capture limit (in bytes).</summary>
    public long? WriteBytesLimit { get; }
}
