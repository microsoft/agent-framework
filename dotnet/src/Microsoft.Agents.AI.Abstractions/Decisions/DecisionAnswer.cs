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

/// <summary>
/// The answer to a <see cref="ScoreDecisionQuestion"/>: a continuous score on the ordered scale and the probability
/// distribution over every level.
/// </summary>
/// <remarks>
/// For <c>N</c> levels at positions <c>0 ... N - 1</c>, <see cref="Probabilities"/> contains an entry for every level,
/// each between 0 and 1, summing to approximately 1, and the portable meaning of <see cref="Score"/> is
/// <c>Σ(levelIndex × P(levelIndex))</c>, so <c>0 &lt;= Score &lt;= N - 1</c>. A provider adapter may compute
/// <see cref="Score"/> from the distribution when the provider does not return it. Two answers with the same score can
/// carry very different distributions, which is why the distribution is the portable value. The distribution supplied
/// at construction is validated (values within 0 to 1); the collection itself stays mutable, matching the proposed
/// <c>Microsoft.Extensions.AI</c> shape, so producers that mutate it afterwards own its invariants.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class ScoreDecisionAnswer : DecisionAnswer
{
    private double _score;
    private double? _confidence;

    /// <summary>Initializes a new instance of the <see cref="ScoreDecisionAnswer"/> class.</summary>
    public ScoreDecisionAnswer()
    {
        this.Probabilities = new Dictionary<int, double>();
    }

    /// <summary>Initializes a new instance of the <see cref="ScoreDecisionAnswer"/> class.</summary>
    /// <param name="score">The probability-weighted position on the scale.</param>
    /// <param name="probabilities">The probability of each level, keyed by level index.</param>
    /// <exception cref="ArgumentNullException"><paramref name="probabilities"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentOutOfRangeException"><paramref name="score"/> is not finite.</exception>
    public ScoreDecisionAnswer(double score, IDictionary<int, double> probabilities)
    {
        this.Score = score;
        this.Probabilities = EnsureDistribution(probabilities, nameof(probabilities));
    }

    /// <summary>Gets or sets the probability-weighted position on the scale.</summary>
    /// <exception cref="ArgumentOutOfRangeException">The value is not finite.</exception>
    public double Score
    {
        get => this._score;
        set => this._score = double.IsNaN(value) || double.IsInfinity(value)
            ? throw new ArgumentOutOfRangeException(nameof(value), value, "The score must be a finite number.")
            : value;
    }

    /// <summary>Gets the probability of each level, keyed by the level's index in <see cref="ScoreDecisionQuestion.Levels"/>.</summary>
    public IDictionary<int, double> Probabilities { get; }

    /// <summary>Gets or sets an optional provider-derived confidence in the score, from 0 to 1.</summary>
    /// <exception cref="ArgumentOutOfRangeException">The value is not finite or is outside 0 to 1.</exception>
    public double? Confidence
    {
        get => this._confidence;
        set => this._confidence = EnsureOptionalProbability(value, nameof(value));
    }
}
