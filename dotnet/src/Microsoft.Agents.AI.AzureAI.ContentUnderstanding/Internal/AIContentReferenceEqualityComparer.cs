// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Reference-equality comparer for <see cref="AIContent"/>. Used to build a strip-set keyed on
/// the exact instances the detector found, so two structurally identical attachments are still
/// distinguishable.
/// </summary>
/// <remarks>
/// <see cref="System.Collections.Generic.ReferenceEqualityComparer"/> is internal/protected on
/// netstandard2.0 and net472 — this hand-rolled comparer keeps the provider portable across
/// every TFM in the package.
/// </remarks>
internal sealed class AIContentReferenceEqualityComparer : IEqualityComparer<AIContent>
{
    public static AIContentReferenceEqualityComparer Instance { get; } = new();

    private AIContentReferenceEqualityComparer()
    {
    }

    public bool Equals(AIContent? x, AIContent? y) => ReferenceEquals(x, y);

    public int GetHashCode(AIContent obj) => System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(obj);
}
