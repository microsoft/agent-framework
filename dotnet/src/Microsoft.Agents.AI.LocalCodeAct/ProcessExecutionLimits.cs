// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// Resource limits for subprocess code execution.
/// </summary>
/// <remarks>
/// These limits provide defense-in-depth controls to prevent runaway code execution,
/// but are NOT a security sandbox. Real sandboxing must come from external container/VM
/// isolation (e.g., Foundry hosted agents, Docker, Azure Container Instances, etc.).
/// </remarks>
public sealed record ProcessExecutionLimits
{
    /// <summary>
    /// Maximum execution time in seconds. Default is 30 seconds.
    /// </summary>
    public int TimeoutSeconds { get; init; } = 30;

    /// <summary>
    /// Maximum bytes of stdout captured. Default is 10MB.
    /// </summary>
    public int MaxStdoutBytes { get; init; } = 10 * 1024 * 1024;

    /// <summary>
    /// Maximum bytes of stderr captured. Default is 10MB.
    /// </summary>
    public int MaxStderrBytes { get; init; } = 10 * 1024 * 1024;

    /// <summary>
    /// Maximum bytes written per file in read-write mounts. Default is 1MB.
    /// </summary>
    public int MaxFileBytesPerFile { get; init; } = 1024 * 1024;

    /// <summary>
    /// Maximum total bytes written across all read-write mounts. Default is 10MB.
    /// </summary>
    public int MaxFileBytesTotal { get; init; } = 10 * 1024 * 1024;
}
