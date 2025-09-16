// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.Workflows.Declarative.PowerFx;

/// <summary>
/// Represents the absence of an assigned value for a variable used in an expression.
/// </summary>
public sealed record class UnassignedValue
{
    /// <summary>
    /// A singleton instance of <see cref="UnassignedValue"/>.
    /// </summary>
    public static UnassignedValue Instance { get; } = new();
}
