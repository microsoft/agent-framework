// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents the response of an <see cref="IDecisionClient"/>: one <see cref="DecisionAnswer"/> per question, keyed by
/// <see cref="DecisionQuestion.Id"/>, plus what answered and what it cost.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class DecisionResponse
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DecisionResponse"/> class with an empty answer set.
    /// </summary>
    public DecisionResponse()
    {
        this.Answers = new Dictionary<string, DecisionAnswer>();
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="DecisionResponse"/> class.
    /// </summary>
    /// <param name="answers">The answers, keyed by question identifier.</param>
    /// <exception cref="System.ArgumentNullException"><paramref name="answers"/> is <see langword="null"/>.</exception>
    public DecisionResponse(IDictionary<string, DecisionAnswer> answers)
    {
        this.Answers = Throw.IfNull(answers);
    }

    /// <summary>Gets the answers, keyed by the <see cref="DecisionQuestion.Id"/> of the question each answers.</summary>
    /// <remarks>
    /// A provider returns an answer of the matching kind for every question in the request. A missing or mismatched
    /// answer is a protocol error the provider surfaces as a <see cref="DecisionClientException"/> rather than an absent key.
    /// </remarks>
    public IDictionary<string, DecisionAnswer> Answers { get; }

    /// <summary>Gets or sets the identifier of the response, when the provider supplies one.</summary>
    public string? ResponseId { get; set; }

    /// <summary>Gets or sets the identifier of the model that produced the answers.</summary>
    /// <remarks>
    /// This is the resolved identifier the provider reports (for example the versioned build behind a moving alias), which
    /// is what provenance should record, not the identifier that was requested.
    /// </remarks>
    public string? ModelId { get; set; }

    /// <summary>Gets or sets usage details for the call, when the provider reports them.</summary>
    public UsageDetails? Usage { get; set; }

    /// <summary>Gets or sets the raw, provider-specific representation of the response, when available.</summary>
    public object? RawRepresentation { get; set; }

    /// <summary>Gets or sets any additional, provider-specific properties associated with the response.</summary>
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }
}
