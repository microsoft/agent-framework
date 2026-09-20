// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// The answer to a <see cref="BinaryDecisionQuestion"/>: the model-reported probability that the proposition is true.
/// </summary>
/// <remarks>
/// The probability is the whole answer. There is no separate confidence: <c>P(false) = 1 - P(true)</c>. A value near 1
/// supports true, a value near 0 supports false, and a value near 0.5 is uncertain. It is a model-reported probability,
/// not an empirically calibrated accuracy.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class BinaryDecisionAnswer : DecisionAnswer
{
    private double _trueProbability;

    /// <summary>Initializes a new instance of the <see cref="BinaryDecisionAnswer"/> class.</summary>
    public BinaryDecisionAnswer()
    {
    }

    /// <summary>Initializes a new instance of the <see cref="BinaryDecisionAnswer"/> class.</summary>
    /// <param name="trueProbability">The probability that the proposition is true.</param>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="trueProbability"/> is not finite or is outside 0 to 1.</exception>
    public BinaryDecisionAnswer(double trueProbability)
    {
        this.TrueProbability = trueProbability;
    }

    /// <summary>Gets or sets the probability, from 0 to 1, that the proposition is true.</summary>
    /// <exception cref="ArgumentOutOfRangeException">The value is not finite or is outside 0 to 1.</exception>
    public double TrueProbability
    {
        get => this._trueProbability;
        set => this._trueProbability = EnsureProbability(value, nameof(value));
    }
}
