// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A question that selects exactly one member of a caller-defined, unordered set of choices, reported as a
/// <see cref="ChoiceDecisionAnswer"/> carrying the selection and a probability distribution over every choice.
/// </summary>
/// <remarks>
/// Choice names must be unique within the question. Their descriptions provide semantic criteria and impose no
/// ordering; for an ordered scale use <see cref="ScoreDecisionQuestion"/>. A choice needs at least two members.
/// Providers may impose an upper limit; that limit is not part of this contract.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class ChoiceDecisionQuestion : DecisionQuestion
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ChoiceDecisionQuestion"/> class.
    /// </summary>
    /// <param name="id">The identifier of the question, unique within a request.</param>
    /// <param name="instructions">The classification question to evaluate against the state.</param>
    /// <param name="choices">The choices to select from.</param>
    /// <exception cref="ArgumentNullException"><paramref name="choices"/> is <see langword="null"/> or contains a <see langword="null"/> element.</exception>
    /// <exception cref="ArgumentException"><paramref name="choices"/> has fewer than two members or contains duplicate names.</exception>
    public ChoiceDecisionQuestion(string id, string instructions, IEnumerable<DecisionChoice> choices)
        : base(id, instructions)
    {
        _ = Throw.IfNull(choices);

        var list = new List<DecisionChoice>();
        var names = new HashSet<string>(StringComparer.Ordinal);
        foreach (DecisionChoice choice in choices)
        {
            _ = Throw.IfNull(choice, nameof(choices));
            if (!names.Add(choice.Name))
            {
                throw new ArgumentException($"Choice names must be unique within a question; '{choice.Name}' appears more than once.", nameof(choices));
            }

            list.Add(choice);
        }

        if (list.Count < 2)
        {
            throw new ArgumentException("A choice question needs at least two choices.", nameof(choices));
        }

        this.Choices = list;
    }

    /// <summary>Gets the choices to select from.</summary>
    public IList<DecisionChoice> Choices { get; }
}

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
