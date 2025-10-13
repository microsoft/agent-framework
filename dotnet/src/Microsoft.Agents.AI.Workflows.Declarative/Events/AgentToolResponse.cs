// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents a user input response.
/// </summary>
public sealed class AgentToolResponse
{
    /// <summary>
    /// The name of the agent associated with the tool response.
    /// </summary>
    public string AgentName { get; }

    /// <summary>
    /// A list of tool responses.
    /// </summary>
    public IReadOnlyList<FunctionResultContent> FunctionResults { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="InputResponse"/> class.
    /// </summary>
    public AgentToolResponse(string agentName, params IEnumerable<FunctionResultContent> functionResults)
    {
        this.AgentName = agentName;
        this.FunctionResults = functionResults.ToImmutableArray();
    }

    internal static AgentToolResponse Create(AgentToolRequest toolRequest, params IEnumerable<FunctionResultContent> functionResults) =>
        // %%% TOOL: VERIFY MATCH
        new(toolRequest.AgentName, functionResults);
}
