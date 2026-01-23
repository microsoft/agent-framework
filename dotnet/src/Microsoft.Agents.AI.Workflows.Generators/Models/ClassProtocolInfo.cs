// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Generators.Models;

/// <summary>
/// Represents protocol type information extracted from class-level [SendsMessage] or [YieldsOutput] attributes.
/// Used by the incremental generator pipeline to capture classes that declare protocol types
/// but may not have [MessageHandler] methods (e.g., when ConfigureRoutes is manually implemented).
/// </summary>
/// <param name="ClassKey">Unique identifier for the class (fully qualified name).</param>
/// <param name="Namespace">The namespace of the class.</param>
/// <param name="ClassName">The name of the class.</param>
/// <param name="GenericParameters">The generic type parameters (e.g., "&lt;T&gt;"), or null if not generic.</param>
/// <param name="IsNested">Whether the class is nested inside another class.</param>
/// <param name="ContainingTypeChain">The chain of containing types for nested classes. Empty if not nested.</param>
/// <param name="IsPartialClass">Whether the class is declared as partial.</param>
/// <param name="DerivesFromExecutor">Whether the class derives from Executor.</param>
/// <param name="HasManualConfigureRoutes">Whether the class has a manually defined ConfigureRoutes method.</param>
/// <param name="ClassLocation">Location info for diagnostics.</param>
/// <param name="TypeName">The fully qualified type name from the attribute.</param>
/// <param name="AttributeKind">Whether this is from a SendsMessage or YieldsOutput attribute.</param>
internal sealed record ClassProtocolInfo(
    string ClassKey,
    string? Namespace,
    string ClassName,
    string? GenericParameters,
    bool IsNested,
    string ContainingTypeChain,
    bool IsPartialClass,
    bool DerivesFromExecutor,
    bool HasManualConfigureRoutes,
    DiagnosticLocationInfo? ClassLocation,
    string TypeName,
    ProtocolAttributeKind AttributeKind)
{
    /// <summary>
    /// Gets an empty result for invalid targets.
    /// </summary>
    public static ClassProtocolInfo Empty { get; } = new(
        string.Empty, null, string.Empty, null, false, string.Empty,
        false, false, false, null, string.Empty, ProtocolAttributeKind.Send);
}
