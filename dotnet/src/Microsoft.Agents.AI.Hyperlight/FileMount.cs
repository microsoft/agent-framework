// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hyperlight;

/// <summary>
/// Represents a host-to-sandbox file mount configuration used by
/// <see cref="HyperlightCodeActProvider"/>.
/// </summary>
public sealed class FileMount
{
    /// <summary>
    /// Initializes a new instance of the <see cref="FileMount"/> class.
    /// </summary>
    /// <param name="hostPath">Absolute or relative path on the host filesystem to mount into the sandbox.</param>
    /// <param name="mountPath">
    /// Path inside the sandbox the host path is exposed at (for example <c>"/input/data.csv"</c>).
    /// </param>
    public FileMount(string hostPath, string mountPath)
    {
        this.HostPath = hostPath;
        this.MountPath = mountPath;
    }

    /// <summary>Gets the path on the host filesystem that is mounted into the sandbox.</summary>
    public string HostPath { get; }

    /// <summary>Gets the path inside the sandbox at which the host path is exposed.</summary>
    public string MountPath { get; }
}
