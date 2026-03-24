// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Immutable;
using Microsoft.CodeAnalysis;

namespace Microsoft.Agents.AI.Workflows.Generators.Models;

/// <summary>
/// Represents the result of analyzing a class with [MessageHandler] attributed methods.
/// Combines the executor info (if valid) with any diagnostics to report.
/// Note: Instances of this class should not be used within the analyzers caching
/// layer because it directly contains a collection of <see cref="Diagnostic"/> objects.
/// </summary>
/// <param name="executorInfo">The executor information.</param>
/// <param name="diagnostics">Any diagnostics to report.</param>
internal sealed class AnalysisResult(ExecutorInfo? executorInfo, ImmutableArray<Diagnostic> diagnostics)
{
    /// <summary>
    /// Gets the executor information.
    /// </summary>
    public ExecutorInfo? ExecutorInfo { get; } = executorInfo;

    /// <summary>
    /// Gets the diagnostics to report.
    /// </summary>
    public ImmutableArray<Diagnostic> Diagnostics { get; } = diagnostics.IsDefault ? ImmutableArray<Diagnostic>.Empty : diagnostics;

    /// <summary>
    /// Creates a successful result with executor info and no diagnostics.
    /// </summary>
    public static AnalysisResult Success(ExecutorInfo info) =>
        new(info, ImmutableArray<Diagnostic>.Empty);

    /// <summary>
    /// Creates a result with only diagnostics (no valid executor info).
    /// </summary>
    public static AnalysisResult WithDiagnostics(ImmutableArray<Diagnostic> diagnostics) =>
        new(null, diagnostics);

    /// <summary>
    /// Creates a result with executor info and diagnostics.
    /// </summary>
    public static AnalysisResult WithInfoAndDiagnostics(ExecutorInfo info, ImmutableArray<Diagnostic> diagnostics) =>
        new(info, diagnostics);

    /// <summary>
    /// Creates an empty result (no info, no diagnostics).
    /// </summary>
    public static AnalysisResult Empty => new(null, ImmutableArray<Diagnostic>.Empty);
}
