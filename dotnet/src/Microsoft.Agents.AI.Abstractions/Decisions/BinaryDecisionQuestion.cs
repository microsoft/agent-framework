// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// A question whose answer is the probability that a proposition is true for the state, reported as a
/// <see cref="BinaryDecisionAnswer"/>.
/// </summary>
/// <remarks>
/// Phrase the proposition so that a high probability means "yes". The answer has no separate confidence value: the
/// probability already describes the two-outcome distribution (<c>P(false) = 1 - P(true)</c>). Use
/// <see cref="Criteria"/> to sharpen the boundary between the two outcomes when it is subtle.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class BinaryDecisionQuestion : DecisionQuestion
{
    /// <summary>
    /// Initializes a new instance of the <see cref="BinaryDecisionQuestion"/> class.
    /// </summary>
    /// <param name="id">The identifier of the question, unique within a request.</param>
    /// <param name="instructions">The proposition to evaluate against the state.</param>
    public BinaryDecisionQuestion(string id, string instructions)
        : base(id, instructions)
    {
    }

    /// <summary>Gets or sets optional descriptions of what a true and a false answer mean.</summary>
    public BinaryDecisionCriteria? Criteria { get; set; }
}

/// <summary>
/// Describes what a true and a false answer to a <see cref="BinaryDecisionQuestion"/> mean, to sharpen the semantic
/// boundary between them.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class BinaryDecisionCriteria
{
    /// <summary>Gets or sets a description of what a true answer means.</summary>
    public string? TrueDescription { get; set; }

    /// <summary>Gets or sets a description of what a false answer means.</summary>
    public string? FalseDescription { get; set; }
}
