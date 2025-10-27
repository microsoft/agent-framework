// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents one or more user-input requests.
/// </summary>
public sealed class UserInputRequest
{
    /// <summary>
    /// The name of the agent associated with the tool request.
    /// </summary>
    public string AgentName { get; }

    /// <summary>
    /// A list of user input requests.
    /// </summary>
    public IList<AIContent> InputRequests { get; }

    [JsonConstructor]
    internal UserInputRequest(string agentName, IList<AIContent> inputRequests)
    {
        this.AgentName = agentName;
        this.InputRequests = inputRequests;
    }
}
