// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// The raw options of a <see cref="JevDecisionClient"/> request, returned by
/// <see cref="DecisionOptions.RawRepresentationFactory"/>.
/// </summary>
internal sealed class JevDecisionRequestOptions
{
    /// <summary>
    /// Gets the Jev questions to send instead of the decision questions with the same IDs.
    /// </summary>
    /// <remarks>
    /// Jev questions can hold JSON instructions and criteria, which decision questions carry only as text. A caller
    /// that has the Jev questions passes them here, so the API receives them unchanged, and the decision questions
    /// only correlate the answers.
    /// </remarks>
    public IReadOnlyDictionary<string, JevQuestion>? Questions { get; init; }
}
