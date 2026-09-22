// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a bounded, typed question that an <see cref="IDecisionClient"/> evaluates against a
/// <see cref="DecisionRequest.State"/>. The concrete kinds are <see cref="BinaryDecisionQuestion"/>,
/// <see cref="ChoiceDecisionQuestion"/>, and <see cref="ScoreDecisionQuestion"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class DecisionQuestion
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DecisionQuestion"/> class.
    /// </summary>
    /// <param name="id">The identifier of the question, unique within a request. Answers are keyed by it.</param>
    /// <param name="instructions">What is being asked about the state.</param>
    /// <exception cref="System.ArgumentNullException"><paramref name="id"/> or <paramref name="instructions"/> is <see langword="null"/>.</exception>
    /// <exception cref="System.ArgumentException"><paramref name="id"/> or <paramref name="instructions"/> is empty or whitespace.</exception>
    protected DecisionQuestion(string id, string instructions)
    {
        this.Id = Throw.IfNullOrWhitespace(id);
        this.Instructions = Throw.IfNullOrWhitespace(instructions);
    }

    /// <summary>Gets the identifier of the question. Answers in a <see cref="DecisionResponse"/> are keyed by it.</summary>
    /// <remarks>Identifiers are application correlation keys; a provider must not attach model semantics to them.</remarks>
    public string Id { get; }

    /// <summary>Gets or sets what is being asked about the state.</summary>
    public string Instructions { get; set; }

    /// <summary>Gets or sets any additional, provider-specific properties associated with the question.</summary>
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }
}
