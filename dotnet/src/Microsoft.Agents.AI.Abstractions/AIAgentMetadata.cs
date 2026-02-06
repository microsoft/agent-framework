// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Text.Json;
using System.Threading;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides metadata information about an <see cref="AIAgent"/> instance.
/// </summary>
/// <remarks>
/// This class contains descriptive information about an agent that can be used for identification,
/// telemetry, and logging purposes.
/// </remarks>
[DebuggerDisplay("ProviderName = {ProviderName}")]
public sealed class AIAgentMetadata
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AIAgentMetadata"/> class.
    /// </summary>
    /// <param name="providerName">
    /// The name of the agent provider, if applicable. Where possible, this should map to the
    /// appropriate name defined in the OpenTelemetry Semantic Conventions for Generative AI systems.
    /// </param>
    /// <param name="supportsStructuredOutput">
    /// Indicates whether the agent supports structured output via <see cref="AIAgent.RunAsync{T}(AgentSession?, JsonSerializerOptions?, AgentRunOptions?, CancellationToken)"/>.
    /// </param>
    public AIAgentMetadata(string? providerName = null, bool supportsStructuredOutput = false)
    {
        this.ProviderName = providerName;
        this.SupportsStructuredOutput = supportsStructuredOutput;
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
    /// Gets a value indicating whether the agent supports structured output.
    /// </summary>
    /// <value>
    /// <see langword="true"/> if the agent supports structured output via <see cref="AIAgent.RunAsync{T}(AgentSession?, JsonSerializerOptions?, AgentRunOptions?, CancellationToken)"/>;
    /// otherwise, <see langword="false"/>.
    /// </value>
    /// <remarks>
    /// Consumers can check this property before calling <see cref="AIAgent.RunAsync{T}(AgentSession?, JsonSerializerOptions?, AgentRunOptions?, CancellationToken)"/>
    /// to determine if the agent supports structured output.
    /// </remarks>
    public bool SupportsStructuredOutput { get; }
}
