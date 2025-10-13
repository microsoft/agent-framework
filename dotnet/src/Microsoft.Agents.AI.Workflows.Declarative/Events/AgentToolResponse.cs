// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using System.Text.Json.Serialization;
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
    [JsonConstructor]
    internal AgentToolResponse(string agentName, params IEnumerable<FunctionResultContent> functionResults)
    {
        this.AgentName = agentName;
        this.FunctionResults = functionResults.ToImmutableArray();
    }

    internal static AgentToolResponse Create(AgentToolRequest toolRequest, params IEnumerable<FunctionResultContent> functionResults)
    {
        HashSet<string> callIds = toolRequest.FunctionCalls.Select(call => call.CallId).ToHashSet();
        HashSet<string> resultIds = functionResults.Select(call => call.CallId).ToHashSet();
        if (!callIds.SetEquals(resultIds))
        {
            throw new DeclarativeActionException("Mismatched function call IDs between request and results."); // %%% EXECEPTION MESSAGE
        }
        return new AgentToolResponse(toolRequest.AgentName, functionResults);
    }
}
