// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents one or more function tool requests.
/// </summary>
public sealed class AgentFunctionToolRequest
{
    /// <summary>
    /// The name of the agent associated with the tool request.
    /// </summary>
    public string AgentName { get; }

    /// <summary>
    /// A list of function tool requests.
    /// </summary>
    public IList<FunctionCallContent> FunctionCalls { get; }

    [JsonConstructor]
    internal AgentFunctionToolRequest(string agentName, IList<FunctionCallContent> functionCalls)
    {
        this.AgentName = agentName;
        this.FunctionCalls = functionCalls;
    }
}
