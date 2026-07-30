// Copyright (c) Microsoft. All rights reserved.

namespace VerifySamples;

/// <summary>
/// The result of verifying a single sample.
/// </summary>
internal sealed class VerificationResult
{
    public required string SampleName { get; init; }
    public required bool Passed { get; init; }
    public required string Summary { get; init; }
    public List<string> Failures { get; init; } = [];
    public string? AIReasoning { get; init; }

    /// <summary>
    /// The sample's stdout output, captured for log file output.
    /// </summary>
    public string? Stdout { get; init; }

    /// <summary>
    /// The sample's stderr output, captured for log file output.
    /// </summary>
    public string? Stderr { get; init; }

    /// <summary>
    /// Per-sample log lines, buffered during parallel execution
    /// and written sequentially to the log file.
    /// </summary>
    public List<string> LogLines { get; init; } = [];
}
