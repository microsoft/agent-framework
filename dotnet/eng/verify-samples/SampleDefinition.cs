// Copyright (c) Microsoft. All rights reserved.

namespace VerifySamples;

/// <summary>
/// Describes a sample to verify, including its expected output.
/// </summary>
internal sealed class SampleDefinition
{
    /// <summary>
    /// Display name for the sample (e.g., "01_hello_agent").
    /// </summary>
    public required string Name { get; init; }

    /// <summary>
    /// Relative path from the dotnet/ directory to the sample project directory.
    /// </summary>
    public required string ProjectPath { get; init; }

    /// <summary>
    /// Environment variables that the sample requires for a meaningful run.
    /// The runner checks these before running and will skip the sample if any are unset,
    /// recording a skip reason that indicates which required variables are missing.
    /// </summary>
    public string[] RequiredEnvironmentVariables { get; init; } = [];

    /// <summary>
    /// Environment variables that the sample can use but typically has fallbacks or defaults for.
    /// If these are not set, the sample might prompt or behave interactively, which could cause
    /// automated verification to hang. The runner checks these and skips the sample if they are unset
    /// to avoid non-deterministic or blocking behavior in automated runs.
    /// </summary>
    public string[] OptionalEnvironmentVariables { get; init; } = [];

    /// <summary>
    /// If set, the sample is skipped with this reason.
    /// Use only for structural reasons (e.g., web server, multi-process, needs external service).
    /// Do NOT use for missing environment variables — those are checked dynamically.
    /// </summary>
    public string? SkipReason { get; init; }

    /// <summary>
    /// Substrings that must appear in stdout for the sample to pass.
    /// Used for deterministic verification.
    /// </summary>
    public string[] MustContain { get; init; } = [];

    /// <summary>
    /// Substrings that must not appear in stdout for the sample to pass.
    /// </summary>
    public string[] MustNotContain { get; init; } = [];

    /// <summary>
    /// If true, <see cref="MustContain"/> entries cover the entire expected output —
    /// no AI verification is needed.
    /// </summary>
    public bool IsDeterministic { get; init; }

    /// <summary>
    /// Natural-language description of what the sample output should look like.
    /// Used by the AI verifier for non-deterministic samples.
    /// Each entry describes one aspect of the expected output that should be verified.
    /// </summary>
    public string[] ExpectedOutputDescription { get; init; } = [];

    /// <summary>
    /// Sequence of stdin inputs to feed to the sample process.
    /// Each entry is written as a line (followed by newline) to the process stdin.
    /// A <c>null</c> entry inserts a delay without writing anything.
    /// Inputs are sent with a short delay between each to allow the process to prompt.
    /// </summary>
    public string?[] Inputs { get; init; } = [];

    /// <summary>
    /// Delay in milliseconds between each input line. Default is 2000ms.
    /// Increase for samples that need more time between prompts (e.g., LLM calls between inputs).
    /// </summary>
    public int InputDelayMs { get; init; } = 2000;
}
