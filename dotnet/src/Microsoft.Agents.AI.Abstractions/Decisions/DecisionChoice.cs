// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// One member of a <see cref="ChoiceDecisionQuestion"/>'s choice set.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class DecisionChoice
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DecisionChoice"/> class.
    /// </summary>
    /// <param name="name">The name of the choice. It is the key of the choice in <see cref="ChoiceDecisionAnswer.Probabilities"/>.</param>
    /// <param name="description">An optional description of what the choice means.</param>
    /// <exception cref="ArgumentNullException"><paramref name="name"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentException"><paramref name="name"/> is empty or whitespace.</exception>
    public DecisionChoice(string name, string? description = null)
    {
        this.Name = Throw.IfNullOrWhitespace(name);
        this.Description = description;
    }

    /// <summary>Gets the name of the choice.</summary>
    public string Name { get; }

    /// <summary>Gets or sets an optional description of what the choice means.</summary>
    public string? Description { get; set; }
}
