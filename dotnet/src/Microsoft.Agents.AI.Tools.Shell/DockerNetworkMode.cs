// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Tools.Shell;

/// <summary>
/// Well-known values for the <c>network</c> parameter on
/// <see cref="DockerShellExecutor"/>. The parameter type stays
/// <see langword="string"/> so callers can supply user-defined networks
/// (e.g. <c>"my-private-net"</c>) — these constants exist for
/// discoverability and to avoid stringly-typed defaults.
/// </summary>
public static class DockerNetworkMode
{
    /// <summary>No network — the container has no network interfaces. The default.</summary>
    public const string None = "none";

    /// <summary>Docker's default bridge network — egress to the host network.</summary>
    public const string Bridge = "bridge";

    /// <summary>Share the host's network namespace — strongly discouraged for untrusted code.</summary>
    public const string Host = "host";
}
