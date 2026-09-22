// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

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
