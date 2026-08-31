// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>
/// A reference to a generated rubric evaluator that already exists in the provider's registry.
/// </summary>
/// <remarks>
/// <para>
/// Pass instances of this class to a batch evaluator (for example
/// <c>Microsoft.Agents.AI.Foundry.FoundryEvals</c>) to score items with a pre-existing rubric
/// evaluator that was authored in the provider's portal or via the provider's dedicated SDK.
/// Agent Framework is a consumer here: it does not create or modify the evaluator definition;
/// it only references the persisted version by name.
/// </para>
/// <para>
/// Pinning <see cref="Version"/> is strongly recommended so evaluation runs are reproducible.
/// A <see langword="null"/> <see cref="Version"/> resolves to whichever version is current at
/// execution time; consuming evaluators are expected to emit a warning when a versionless
/// reference is used. CI gates should always pass a concrete version.
/// </para>
/// </remarks>
/// <param name="Name">
/// Evaluator name as stored in the provider's registry (for example
/// <c>"reservation-policy-rubric"</c>). Distinct from built-in evaluators such as
/// <c>"relevance"</c>.
/// </param>
/// <param name="Version">
/// Pinned evaluator version. <see langword="null"/> means "latest" — this is discouraged for
/// reproducible runs and consumers may emit a warning when used.
/// </param>
/// <param name="DisplayName">
/// Optional human-readable name used in result summaries. Defaults to <see cref="Name"/> when
/// unset.
/// </param>
public sealed record GeneratedEvaluatorRef(
    string Name,
    string? Version = null,
    string? DisplayName = null)
{
    /// <summary>
    /// Creates a versionless reference that resolves to the latest version of the evaluator at
    /// run time.
    /// </summary>
    /// <remarks>
    /// Discouraged for reproducible runs. Prefer the primary constructor with an explicit
    /// <see cref="Version"/> so CI and replay evaluations stay stable when the evaluator is
    /// updated in the provider's registry.
    /// </remarks>
    /// <param name="name">Evaluator name as stored in the provider's registry.</param>
    /// <param name="displayName">Optional human-readable name used in result summaries.</param>
    /// <returns>A new <see cref="GeneratedEvaluatorRef"/> with <see cref="Version"/> unset.</returns>
    public static GeneratedEvaluatorRef Latest(string name, string? displayName = null)
        => new(name, Version: null, DisplayName: displayName);
}
