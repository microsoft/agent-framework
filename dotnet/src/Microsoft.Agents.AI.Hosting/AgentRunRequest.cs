// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Represents a request to run an agent with a collection of chat messages.
/// </summary>
public sealed class AgentRunRequest
{
    /// <summary>
    /// Gets or sets the collection of chat messages to be processed by the agent.
    /// </summary>
    [JsonPropertyName("messages")]
    public List<ChatMessage>? Messages { get; set; }
}
