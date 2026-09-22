// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// The answer to a <see cref="ChoiceDecisionQuestion"/>: the selected choice and the probability distribution over
/// every choice.
/// </summary>
/// <remarks>
/// <see cref="Probabilities"/> is the fundamental interoperable value: it contains an entry for every requested choice,
/// each between 0 and 1, summing to approximately 1. <see cref="SelectedChoice"/> is one of the requested choices.
/// <see cref="Confidence"/> is an optional provider-derived summary of the distribution and is not comparable across
/// providers unless documented. The distribution supplied at construction is validated (non-blank keys, values within
/// 0 to 1); the collection itself stays mutable, matching the proposed <c>Microsoft.Extensions.AI</c> shape, so
/// producers that mutate it afterwards own its invariants.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class ChoiceDecisionAnswer : DecisionAnswer
{
    private double? _confidence;
    private string _selectedChoice;

    /// <summary>Initializes a new instance of the <see cref="ChoiceDecisionAnswer"/> class.</summary>
    /// <param name="selectedChoice">The name of the selected choice.</param>
    /// <param name="probabilities">The probability of each choice, keyed by choice name.</param>
    /// <exception cref="ArgumentNullException"><paramref name="selectedChoice"/> or <paramref name="probabilities"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="selectedChoice"/> is empty or whitespace.</exception>
    public ChoiceDecisionAnswer(string selectedChoice, IDictionary<string, double> probabilities)
    {
        this._selectedChoice = Throw.IfNullOrWhitespace(selectedChoice);
        this.Probabilities = EnsureDistribution(probabilities, nameof(probabilities));
    }

    /// <summary>Gets or sets the name of the selected choice.</summary>
    /// <exception cref="ArgumentNullException">The value is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException">The value is empty or whitespace.</exception>
    public string SelectedChoice
    {
        get => this._selectedChoice;
        set => this._selectedChoice = Throw.IfNullOrWhitespace(value);
    }

    /// <summary>Gets the probability of each choice, keyed by <see cref="DecisionChoice.Name"/>.</summary>
    public IDictionary<string, double> Probabilities { get; }

    /// <summary>Gets or sets an optional provider-derived confidence in <see cref="SelectedChoice"/>, from 0 to 1.</summary>
    /// <exception cref="ArgumentOutOfRangeException">The value is not finite or is outside 0 to 1.</exception>
    public double? Confidence
    {
        get => this._confidence;
        set => this._confidence = EnsureOptionalProbability(value, nameof(value));
    }
}
