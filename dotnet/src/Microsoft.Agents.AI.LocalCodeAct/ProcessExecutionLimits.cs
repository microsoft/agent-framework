// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// Resource limits for subprocess code execution.
/// </summary>
/// <remarks>
/// These limits provide defense-in-depth controls to prevent runaway code execution,
/// but are NOT a security sandbox. Real sandboxing must come from external container/VM
/// isolation (for example, Foundry hosted agents, Docker, or Azure Container Instances).
/// </remarks>
public sealed class ProcessExecutionLimits
{
    /// <summary>Gets or sets the maximum execution time for the subprocess, in seconds. Default is 30.</summary>
    public int TimeoutSeconds { get; set; } = 30;

    /// <summary>Gets or sets the maximum time the AST validator subprocess may run, in seconds. Default is 10.</summary>
    public int ValidationTimeoutSeconds { get; set; } = 10;

    /// <summary>Gets or sets the maximum bytes of stdout captured from the subprocess. Default is 10 MiB.</summary>
    public int MaxStdoutBytes { get; set; } = 10 * 1024 * 1024;

    /// <summary>Gets or sets the maximum bytes of stderr captured from the subprocess. Default is 10 MiB.</summary>
    public int MaxStderrBytes { get; set; } = 10 * 1024 * 1024;

    /// <summary>Gets or sets the maximum serialized result size in bytes. Default is 10 MiB.</summary>
    public int MaxResultBytes { get; set; } = 10 * 1024 * 1024;

    /// <summary>Gets or sets the maximum bytes captured per file under read-write mounts. Default is 1 MiB.</summary>
    public int MaxCapturedFileBytes { get; set; } = 1024 * 1024;

    /// <summary>Gets or sets the maximum total bytes captured across all read-write mounts. Default is 10 MiB.</summary>
    public int MaxTotalCapturedFileBytes { get; set; } = 10 * 1024 * 1024;
}
