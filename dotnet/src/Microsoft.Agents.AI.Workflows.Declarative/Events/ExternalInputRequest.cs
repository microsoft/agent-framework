// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents a request for external input.
/// </summary>
public sealed class ExternalInputRequest
{
    /// <summary>
    /// The source message that triggered the request for external input.
    /// </summary>
    public AgentRunResponse AgentResponse { get; }

    [JsonConstructor]
    internal ExternalInputRequest(AgentRunResponse agentResponse)
    {
        this.AgentResponse = agentResponse;
    }
}
