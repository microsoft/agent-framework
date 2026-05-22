// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Globalization;

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// UID/GID pair passed to <c>docker run --user</c>.
/// </summary>
/// <param name="Uid">User ID (numeric string, e.g. <c>"65534"</c>; <c>"root"</c> or <c>"0"</c> selects the container's root user).</param>
/// <param name="Gid">Group ID (numeric string).</param>
public sealed record ContainerUser(string Uid, string Gid)
{
    /// <summary>
    /// Default unprivileged user (<c>nobody:nogroup</c> on most distros, UID/GID 65534).
    /// </summary>
    public static ContainerUser Default { get; } = new("65534", "65534");

    /// <summary>
    /// Container root (UID/GID 0). Avoid in production; use only for diagnostics.
    /// </summary>
    public static ContainerUser Root { get; } = new("0", "0");

    /// <summary>Render as the <c>uid:gid</c> string Docker expects.</summary>
    public override string ToString() => $"{this.Uid}:{this.Gid}";

    /// <summary>
    /// Returns <see langword="true"/> when this user maps to UID 0 (root).
    /// </summary>
    public bool IsRoot =>
        this.Uid.Equals("root", StringComparison.OrdinalIgnoreCase)
        || (int.TryParse(this.Uid, NumberStyles.Integer, CultureInfo.InvariantCulture, out var uid) && uid == 0);
}
