// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
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
    public IList<FunctionResultContent> FunctionResults { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="InputResponse"/> class.
    /// </summary>
    [JsonConstructor]
    internal AgentToolResponse(string agentName, IList<FunctionResultContent> functionResults)
    {
        this.AgentName = agentName;
        this.FunctionResults = functionResults;
    }

    /// <summary>
    /// Factory method to create an <see cref="AgentToolResponse"/> from an <see cref="AgentToolRequest"/>
    /// Ensures that all function calls in the request have a corresponding result.
    /// </summary>
    /// <param name="toolRequest">The tool request.</param>
    /// <param name="functionResults">On or more function results</param>
    /// <returns>An <see cref="AgentToolResponse"/> that can be provided to the workflow.</returns>
    /// <exception cref="DeclarativeActionException">Not all <see cref="AgentToolRequest.FunctionCalls"/> have a corresponding <see cref="FunctionResultContent"/>.</exception>
    public static AgentToolResponse Create(AgentToolRequest toolRequest, params IEnumerable<FunctionResultContent> functionResults)
    {
        HashSet<string> callIds = [.. toolRequest.FunctionCalls.Select(call => call.CallId)];
        HashSet<string> resultIds = [.. functionResults.Select(call => call.CallId)];
        if (!callIds.SetEquals(resultIds))
        {
            throw new DeclarativeActionException($"Missing results for: {string.Join(",", callIds.Except(resultIds))}");
        }
        return new AgentToolResponse(toolRequest.AgentName, [.. functionResults]);
    }
}
