// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

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
