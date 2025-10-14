// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents a request for user input.
/// </summary>
public sealed class AgentToolRequest
{
    /// <summary>
    /// The name of the agent associated with the tool request.
    /// </summary>
    public string AgentName { get; }

    /// <summary>
    /// A list of tool requests.
    /// </summary>
    public IList<FunctionCallContent> FunctionCalls { get; }

    [JsonConstructor]
    internal AgentToolRequest(string agentName, IList<FunctionCallContent>? functionCalls = null)
    {
        this.AgentName = agentName;
        this.FunctionCalls = functionCalls ?? [];
    }
}
