// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI;

/// <summary>Provides metadata about an <see cref="AIAgent"/>.</summary>
public class AIAgentMetadata
{
    /// <summary>Initializes a new instance of the <see cref="AIAgentMetadata"/> class.</summary>
    /// <param name="providerName">
    /// The name of the agent provider, if applicable. Where possible, this should map to the
    /// appropriate name defined in the OpenTelemetry Semantic Conventions for Generative AI systems.
    /// </param>
    public AIAgentMetadata(string? providerName = null)
    {
        ProviderName = providerName;
    }

    /// <summary>Gets the name of the chat provider.</summary>
    /// <remarks>
    /// Where possible, this maps to the appropriate name defined in the
    /// OpenTelemetry Semantic Conventions for Generative AI systems.
    /// </remarks>
    public string? ProviderName { get; }
}
