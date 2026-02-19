// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Generators.Models;

/// <summary>
/// Represents the result of analyzing a single method with [MessageHandler].
/// Contains both the method's handler info and class context for grouping.
/// Uses value-equatable types to support incremental generator caching.
/// </summary>
/// <remarks>
/// Class-level validation (IsPartialClass, DerivesFromExecutor, HasManualConfigureRoutes)
/// is extracted here but validated once per class in CombineMethodResults to avoid
/// redundant validation work when a class has multiple handlers.
/// </remarks>
internal sealed record MethodAnalysisResult(
    // Class identification for grouping
    string ClassKey,

    // Class-level info (extracted once per method, will be same for all methods in class)
    string? Namespace,
    string ClassName,
    string? GenericParameters,
    bool IsNested,
    string ContainingTypeChain,
    bool BaseHasConfigureProtocol,
    ImmutableEquatableArray<string> ClassSendTypes,
    ImmutableEquatableArray<string> ClassYieldTypes,

    // Class-level facts (used for validation in CombineMethodResults)
    bool IsPartialClass,
    bool DerivesFromExecutor,
    bool HasManualConfigureRoutes,

    // Class location for diagnostics (value-equatable)
    DiagnosticLocationInfo? ClassLocation,

    // Method-level info (null if method validation failed)
    HandlerInfo? Handler,

    // Method-level diagnostics only (class-level diagnostics created in CombineMethodResults)
    ImmutableEquatableArray<DiagnosticInfo> Diagnostics)
{
    /// <summary>
    /// Gets an empty result for invalid targets (e.g., attribute on non-method).
    /// </summary>
    public static MethodAnalysisResult Empty { get; } = new(
        string.Empty, null, string.Empty, null, false, string.Empty,
        false, ImmutableEquatableArray<string>.Empty, ImmutableEquatableArray<string>.Empty,
        false, false, false,
        null, null, ImmutableEquatableArray<DiagnosticInfo>.Empty);
}
