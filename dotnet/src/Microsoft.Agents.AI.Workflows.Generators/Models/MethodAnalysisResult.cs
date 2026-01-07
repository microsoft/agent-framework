// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Generators.Models;

/// <summary>
/// Represents the result of analyzing a single method with [MessageHandler].
/// Contains both the method's handler info and class context for grouping.
/// Uses value-equatable types to support incremental generator caching.
/// </summary>
internal sealed record MethodAnalysisResult(
    // Class identification for grouping
    string ClassKey,

    // Class-level info (extracted once per method, will be same for all methods in class)
    string? Namespace,
    string ClassName,
    string? GenericParameters,
    bool IsNested,
    string ContainingTypeChain,
    bool BaseHasConfigureRoutes,
    EquatableArray<string> ClassSendTypes,
    EquatableArray<string> ClassYieldTypes,

    // Class-level validation results
    bool IsPartialClass,
    bool DerivesFromExecutor,
    bool HasManualConfigureRoutes,

    // Method-level info (null if method validation failed)
    HandlerInfo? Handler,

    // Any diagnostics from analyzing this method (uses DiagnosticInfo for value equality)
    EquatableArray<DiagnosticInfo> Diagnostics);
