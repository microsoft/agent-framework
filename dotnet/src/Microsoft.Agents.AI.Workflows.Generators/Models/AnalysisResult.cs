// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Immutable;
using Microsoft.CodeAnalysis;

namespace Microsoft.Agents.AI.Workflows.Generators.Models;

/// <summary>
/// Represents the result of analyzing a class with [MessageHandler] methods.
/// Combines the executor info (if valid) with any diagnostics to report.
/// Note: This type is used after the caching layer (in RegisterSourceOutput),
/// so it can contain Diagnostic objects directly.
/// </summary>
internal sealed class AnalysisResult
{
    public ExecutorInfo? ExecutorInfo { get; }
    public ImmutableArray<Diagnostic> Diagnostics { get; }

    public AnalysisResult(ExecutorInfo? executorInfo, ImmutableArray<Diagnostic> diagnostics)
    {
        ExecutorInfo = executorInfo;
        Diagnostics = diagnostics.IsDefault ? ImmutableArray<Diagnostic>.Empty : diagnostics;
    }

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
