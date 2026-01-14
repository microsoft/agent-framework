// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents a request for external input.
/// </summary>
public sealed class ExternalInputRequest
{
    /// <summary>
    /// The source message that triggered the request for external input.
    /// </summary>
    public AgentResponse AgentResponse { get; }

    [JsonConstructor]
    internal ExternalInputRequest(AgentResponse agentResponse)
    {
        this.AgentResponse = agentResponse;
    }

    internal ExternalInputRequest(ChatMessage message)
    {
        this.AgentResponse = new AgentResponse(message);
    }

    internal ExternalInputRequest(string text)
    {
        this.AgentResponse = new AgentResponse(new ChatMessage(ChatRole.User, text));
    }
}
