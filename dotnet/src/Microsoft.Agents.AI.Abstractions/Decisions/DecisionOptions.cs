// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents per-call options for an <see cref="IDecisionClient"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public class DecisionOptions
{
    /// <summary>Gets or sets the model identifier to use for this call, overriding the client's default.</summary>
    /// <remarks>
    /// Pin a versioned identifier when reproducibility matters (tests, calibration, benchmarks); a moving alias can
    /// change what answers between runs.
    /// </remarks>
    public string? ModelId { get; set; }

    /// <summary>Gets or sets any additional, provider-specific properties associated with the options.</summary>
    public AdditionalPropertiesDictionary? AdditionalProperties { get; set; }

    /// <summary>
    /// Gets or sets a callback responsible for creating the raw, provider-specific representation of these options.
    /// </summary>
    /// <remarks>
    /// The underlying <see cref="IDecisionClient"/> implementation may have its own representation of options. When
    /// <see cref="IDecisionClient.GetResponseAsync"/> is invoked with a <see cref="DecisionOptions"/>, that implementation
    /// may convert the provided options into its own representation in order to use it while performing the operation.
    /// For situations where a consumer knows which concrete <see cref="IDecisionClient"/> is being used and how it
    /// represents options, a new instance of that provider-specific type may be returned by this callback for the
    /// <see cref="IDecisionClient"/> to use instead of creating a new instance. The <see cref="IDecisionClient"/>
    /// implementation should then apply any relevant settings from the <see cref="DecisionOptions"/> on top of it.
    /// </remarks>
    public Func<IDecisionClient, object?>? RawRepresentationFactory { get; set; }

    /// <summary>Produces a clone of the current <see cref="DecisionOptions"/> instance.</summary>
    /// <returns>A clone of the current <see cref="DecisionOptions"/> instance.</returns>
    /// <remarks>The clone is shallow: the <see cref="AdditionalProperties"/> dictionary is copied, its values are not.</remarks>
    public virtual DecisionOptions Clone() =>
        new()
        {
            ModelId = this.ModelId,
            AdditionalProperties = this.AdditionalProperties?.Clone(),
            RawRepresentationFactory = this.RawRepresentationFactory,
        };
}
