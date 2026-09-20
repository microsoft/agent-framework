// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides metadata about an <see cref="IDecisionClient"/>, retrievable through <see cref="IDecisionClient.GetService"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public class DecisionClientMetadata
{
    /// <summary>
    /// Initializes a new instance of the <see cref="DecisionClientMetadata"/> class.
    /// </summary>
    /// <param name="providerName">The name of the decision provider, if applicable.</param>
    /// <param name="providerUri">The URL for accessing the decision provider, if applicable.</param>
    /// <param name="defaultModelId">The identifier of the model used by default, if applicable.</param>
    public DecisionClientMetadata(string? providerName = null, Uri? providerUri = null, string? defaultModelId = null)
    {
        this.ProviderName = providerName;
        this.ProviderUri = providerUri;
        this.DefaultModelId = defaultModelId;
    }

    /// <summary>Gets the name of the decision provider.</summary>
    public string? ProviderName { get; }

    /// <summary>Gets the URL for accessing the decision provider.</summary>
    public Uri? ProviderUri { get; }

    /// <summary>Gets the identifier of the model used by default when a request does not specify one.</summary>
    public string? DefaultModelId { get; }
}
