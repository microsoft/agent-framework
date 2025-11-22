// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides metadata information about an <see cref="AIAgent"/> instance.
/// </summary>
/// <remarks>
/// This class contains descriptive information about an agent that can be used for identification,
/// telemetry, and logging purposes.
/// </remarks>
[DebuggerDisplay("ProviderName = {ProviderName}")]
public class AIAgentMetadata
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AIAgentMetadata"/> class.
    /// </summary>
    /// <param name="providerName">
    /// The name of the agent provider, if applicable. Where possible, this should map to the
    /// appropriate name defined in the OpenTelemetry Semantic Conventions for Generative AI systems.
    /// </param>
    /// <param name="additionalProperties">
    /// Additional properties associated with the agent metadata.
    /// </param>
    public AIAgentMetadata(string? providerName = null, AdditionalPropertiesDictionary? additionalProperties = null)
    {
        this.ProviderName = providerName;
        this.AdditionalProperties = additionalProperties;
    }

    /// <summary>
    /// Gets the name of the agent provider.
    /// </summary>
    /// <value>
    /// The provider name that identifies the underlying service or implementation powering the agent.
    /// </value>
    /// <remarks>
    /// Where possible, this maps to the appropriate name defined in the
    /// OpenTelemetry Semantic Conventions for Generative AI systems.
    /// </remarks>
    public string? ProviderName { get; }

    /// <summary>
    /// Gets additional properties associated with the agent metadata.
    /// </summary>
    /// <value>
    /// An <see cref="AdditionalPropertiesDictionary"/> containing custom properties,
    /// or <see langword="null"/> if no additional properties are present.
    /// </value>
    /// <remarks>
    /// Additional properties provide a way to include custom metadata or agent-specific
    /// information that doesn't fit into the standard agent schema.
    /// </remarks>
    public AdditionalPropertiesDictionary? AdditionalProperties { get; }
}
