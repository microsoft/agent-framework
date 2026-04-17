// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Hyperlight;

/// <summary>
/// Represents a host-to-sandbox file mount configuration used by
/// <see cref="HyperlightCodeActProvider"/>.
/// </summary>
/// <param name="HostPath">
/// Absolute or relative path on the host filesystem to mount into the sandbox.
/// </param>
/// <param name="MountPath">
/// Path inside the sandbox the host path is exposed at (for example
/// <c>"/input/data.csv"</c>).
/// </param>
public sealed record FileMount(string HostPath, string MountPath);
