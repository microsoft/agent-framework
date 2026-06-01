// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>
/// Specifies a single evaluator for a <see cref="FoundryEvals"/> run — either a built-in
/// Foundry evaluator (referenced by short or fully-qualified name) or a pre-existing rubric
/// evaluator (referenced by <see cref="GeneratedEvaluatorRef"/>).
/// </summary>
/// <remarks>
/// <para>
/// Both <see cref="string"/> and <see cref="GeneratedEvaluatorRef"/> are implicitly convertible
/// to <see cref="FoundryEvaluatorSpec"/>, so call sites can mix the two:
/// </para>
/// <code>
/// var evals = new FoundryEvals(
///     projectClient,
///     "gpt-4o-mini",
///     new GeneratedEvaluatorRef("policy-rubric", Version: "3"),
///     FoundryEvals.Relevance,
///     FoundryEvals.Coherence);
/// </code>
/// </remarks>
public readonly struct FoundryEvaluatorSpec : IEquatable<FoundryEvaluatorSpec>
{
    private FoundryEvaluatorSpec(string? builtinName, GeneratedEvaluatorRef? generatedRef)
    {
        this.BuiltinName = builtinName;
        this.GeneratedRef = generatedRef;
    }

    /// <summary>
    /// Initializes a new <see cref="FoundryEvaluatorSpec"/> for a built-in evaluator by name
    /// (for example <c>"relevance"</c> or <c>"builtin.relevance"</c>).
    /// </summary>
    /// <param name="builtinName">Built-in evaluator name.</param>
    public FoundryEvaluatorSpec(string builtinName)
        : this(builtinName ?? throw new ArgumentNullException(nameof(builtinName)), null)
    {
    }

    /// <summary>
    /// Initializes a new <see cref="FoundryEvaluatorSpec"/> for a generated rubric evaluator
    /// previously registered with the provider.
    /// </summary>
    /// <param name="generatedRef">Reference to the rubric evaluator.</param>
    public FoundryEvaluatorSpec(GeneratedEvaluatorRef generatedRef)
        : this(null, generatedRef ?? throw new ArgumentNullException(nameof(generatedRef)))
    {
    }

    /// <summary>Gets the built-in evaluator name, or <see langword="null"/> when this is a rubric reference.</summary>
    public string? BuiltinName { get; }

    /// <summary>Gets the rubric reference, or <see langword="null"/> when this is a built-in evaluator.</summary>
    public GeneratedEvaluatorRef? GeneratedRef { get; }

    /// <summary>Gets whether this spec references a built-in evaluator.</summary>
    public bool IsBuiltin => this.BuiltinName is not null;

    /// <summary>Gets whether this spec references a generated rubric evaluator.</summary>
    public bool IsRubric => this.GeneratedRef is not null;

    /// <summary>Implicit conversion from a built-in evaluator name.</summary>
    public static implicit operator FoundryEvaluatorSpec(string builtinName) => new(builtinName);

    /// <summary>Implicit conversion from a <see cref="GeneratedEvaluatorRef"/>.</summary>
    public static implicit operator FoundryEvaluatorSpec(GeneratedEvaluatorRef generatedRef) => new(generatedRef);

    /// <inheritdoc/>
    public bool Equals(FoundryEvaluatorSpec other)
        => this.BuiltinName == other.BuiltinName
            && Equals(this.GeneratedRef, other.GeneratedRef);

    /// <inheritdoc/>
    public override bool Equals(object? obj) => obj is FoundryEvaluatorSpec other && this.Equals(other);

    /// <inheritdoc/>
    public override int GetHashCode()
        => HashCode.Combine(this.BuiltinName, this.GeneratedRef);

    /// <summary>Equality operator.</summary>
    public static bool operator ==(FoundryEvaluatorSpec left, FoundryEvaluatorSpec right) => left.Equals(right);

    /// <summary>Inequality operator.</summary>
    public static bool operator !=(FoundryEvaluatorSpec left, FoundryEvaluatorSpec right) => !left.Equals(right);

    /// <inheritdoc/>
    public override string ToString()
        => this.IsRubric
            ? $"GeneratedEvaluatorRef({this.GeneratedRef!.Name}@{this.GeneratedRef.Version ?? "latest"})"
            : this.BuiltinName ?? "<empty>";
}
