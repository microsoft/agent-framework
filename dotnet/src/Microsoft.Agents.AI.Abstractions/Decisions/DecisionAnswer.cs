// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the typed answer to a <see cref="DecisionQuestion"/>. The concrete kinds are
/// <see cref="BinaryDecisionAnswer"/>, <see cref="ChoiceDecisionAnswer"/>, and <see cref="ScoreDecisionAnswer"/>, each
/// matching the kind of question that produced it.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class DecisionAnswer
{
    /// <summary>Initializes a new instance of the <see cref="DecisionAnswer"/> class.</summary>
    protected DecisionAnswer()
    {
    }

    /// <summary>Gets or sets the raw, provider-specific representation of the answer, when available.</summary>
    public object? RawRepresentation { get; set; }

    /// <summary>Gets or sets any additional, provider-specific properties associated with the answer.</summary>
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }

    /// <summary>Validates that a probability-like value is finite and within 0 to 1 inclusive.</summary>
    /// <param name="value">The value to validate.</param>
    /// <param name="paramName">The name of the member being set.</param>
    /// <returns><paramref name="value"/>.</returns>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="value"/> is not finite or is outside 0 to 1.</exception>
    private protected static double EnsureProbability(double value, string paramName)
    {
        if (double.IsNaN(value) || double.IsInfinity(value) || value < 0 || value > 1)
        {
            throw new ArgumentOutOfRangeException(paramName, value, "The value must be a finite number between 0 and 1 inclusive.");
        }

        return value;
    }

    /// <summary>Validates that an optional confidence value, when present, is finite and within 0 to 1 inclusive.</summary>
    private protected static double? EnsureOptionalProbability(double? value, string paramName) =>
        value is null ? null : EnsureProbability(value.Value, paramName);

    /// <summary>Validates every entry of a distribution supplied at construction: non-blank keys and unit probabilities.</summary>
    private protected static IDictionary<TKey, double> EnsureDistribution<TKey>(IDictionary<TKey, double> probabilities, string paramName)
    {
        _ = Throw.IfNull(probabilities, paramName);
        foreach (KeyValuePair<TKey, double> pair in probabilities)
        {
            if (pair.Key is null || (pair.Key is string key && string.IsNullOrWhiteSpace(key)))
            {
                throw new ArgumentException("Distribution keys must not be null or blank.", paramName);
            }

            _ = EnsureProbability(pair.Value, paramName);
        }

        return probabilities;
    }
}
