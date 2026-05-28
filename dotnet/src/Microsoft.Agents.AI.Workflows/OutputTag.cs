// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Identifies the kind of output that a <see cref="WorkflowOutputEvent"/> represents.
/// A thin <c>ChatRole</c>-style wrapper around a normalized string <see cref="Value"/>,
/// with value equality and a closed set of well-known singletons (the constructor is
/// <see langword="internal"/> for now).
/// </summary>
[JsonConverter(typeof(OutputTagJsonConverter))]
public readonly struct OutputTag : IEquatable<OutputTag>
{
    /// <summary>
    /// The string identifier of the tag. Compared with ordinal equality.
    /// </summary>
    public string? Value { get; }

    internal OutputTag(string value)
    {
        this.Value = Throw.IfNullOrEmpty(value);
    }

    /// <summary>
    /// The tag denoting an intermediate workflow output &#x2014; emitted by executors
    /// registered via <see cref="WorkflowBuilderExtensions.WithIntermediateOutputFrom(WorkflowBuilder, System.Collections.Generic.IEnumerable{ExecutorBinding})"/>.
    /// Terminal (non-intermediate) outputs carry no tag.
    /// </summary>
    public static OutputTag Intermediate { get; } = new("intermediate");

    /// <inheritdoc />
    public bool Equals(OutputTag other) => string.Equals(this.Value, other.Value, StringComparison.Ordinal);

    /// <inheritdoc />
    public override bool Equals(object? obj) => obj is OutputTag other && this.Equals(other);

    /// <inheritdoc />
    public override int GetHashCode() => this.Value is null ? 0 : StringComparer.Ordinal.GetHashCode(this.Value);

    /// <summary>Determines whether two <see cref="OutputTag"/> values are equal.</summary>
    public static bool operator ==(OutputTag left, OutputTag right) => left.Equals(right);

    /// <summary>Determines whether two <see cref="OutputTag"/> values are not equal.</summary>
    public static bool operator !=(OutputTag left, OutputTag right) => !left.Equals(right);

    /// <inheritdoc />
    public override string ToString() => this.Value ?? string.Empty;
}
