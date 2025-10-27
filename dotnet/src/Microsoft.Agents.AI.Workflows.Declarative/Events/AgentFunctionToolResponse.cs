// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents one or more function tool responses.
/// </summary>
public sealed class AgentFunctionToolResponse
{
    /// <summary>
    /// The name of the agent associated with the tool response.
    /// </summary>
    public string AgentName { get; }

    /// <summary>
    /// A list of tool responses.
    /// </summary>
    public IList<FunctionResultContent> FunctionResults { get; }

    [JsonConstructor]
    internal AgentFunctionToolResponse(string agentName, IList<FunctionResultContent> functionResults)
    {
        this.AgentName = agentName;
        this.FunctionResults = functionResults;
    }

    /// <summary>
    /// Factory method to create an <see cref="AgentFunctionToolResponse"/> from an <see cref="AgentFunctionToolRequest"/>
    /// Ensures that all function calls in the request have a corresponding result.
    /// </summary>
    /// <param name="toolRequest">The tool request.</param>
    /// <param name="functionResults">One or more function results</param>
    /// <returns>An <see cref="AgentFunctionToolResponse"/> that can be provided to the workflow.</returns>
    /// <exception cref="DeclarativeActionException">Not all <see cref="AgentFunctionToolRequest.FunctionCalls"/> have a corresponding <see cref="FunctionResultContent"/>.</exception>
    public static AgentFunctionToolResponse Create(AgentFunctionToolRequest toolRequest, params IEnumerable<FunctionResultContent> functionResults)
    {
        HashSet<string> callIds = [.. toolRequest.FunctionCalls.Select(call => call.CallId)];
        HashSet<string> resultIds = [.. functionResults.Select(call => call.CallId)];

        if (!callIds.SetEquals(resultIds))
        {
            throw new DeclarativeActionException($"Missing results for: {string.Join(",", callIds.Except(resultIds))}");
        }

        return new AgentFunctionToolResponse(toolRequest.AgentName, [.. functionResults]);
    }
}
