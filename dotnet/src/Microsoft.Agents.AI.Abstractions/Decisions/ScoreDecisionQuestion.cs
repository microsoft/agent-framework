// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A question that places the state on a caller-defined ordered scale, reported as a <see cref="ScoreDecisionAnswer"/>
/// carrying a continuous score and a probability distribution over every level.
/// </summary>
/// <remarks>
/// The list order of <see cref="Levels"/> defines the ordinal position of each level: <c>Levels[0]</c> is position 0,
/// <c>Levels[1]</c> is position 1, and so on. The portable meaning of <see cref="ScoreDecisionAnswer.Score"/> is the
/// probability-weighted position, <c>Σ(levelIndex × P(levelIndex))</c>. A scale needs at least two levels. Providers may
/// impose an upper limit; that limit is not part of this contract.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class ScoreDecisionQuestion : DecisionQuestion
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ScoreDecisionQuestion"/> class.
    /// </summary>
    /// <param name="id">The identifier of the question, unique within a request.</param>
    /// <param name="instructions">The scoring question to evaluate against the state.</param>
    /// <param name="levels">The levels of the scale, lowest first.</param>
    /// <exception cref="ArgumentNullException"><paramref name="levels"/> is <see langword="null"/> or contains a <see langword="null"/> element.</exception>
    /// <exception cref="ArgumentException"><paramref name="levels"/> has fewer than two members.</exception>
    public ScoreDecisionQuestion(string id, string instructions, IEnumerable<DecisionScoreLevel> levels)
        : base(id, instructions)
    {
        _ = Throw.IfNull(levels);

        var list = new List<DecisionScoreLevel>();
        foreach (DecisionScoreLevel level in levels)
        {
            list.Add(Throw.IfNull(level, nameof(levels)));
        }

        if (list.Count < 2)
        {
            throw new ArgumentException("A score question needs at least two levels.", nameof(levels));
        }

        this.Levels = list;
    }

    /// <summary>Gets the levels of the scale, lowest first. The index of a level is its ordinal position.</summary>
    public IList<DecisionScoreLevel> Levels { get; }
}

/// <summary>
/// One level of a <see cref="ScoreDecisionQuestion"/>'s ordered scale.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class DecisionScoreLevel
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DecisionScoreLevel"/> class.
    /// </summary>
    /// <param name="description">A description of what the level means.</param>
    /// <exception cref="ArgumentNullException"><paramref name="description"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="description"/> is empty or whitespace.</exception>
    public DecisionScoreLevel(string description)
    {
        this.Description = Throw.IfNullOrWhitespace(description);
    }

    /// <summary>Gets or sets a description of what the level means.</summary>
    public string Description { get; set; }
}
