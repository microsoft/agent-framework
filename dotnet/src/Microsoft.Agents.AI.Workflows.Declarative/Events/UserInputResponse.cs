// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents one or more user-input responses.
/// </summary>
public sealed class UserInputResponse
{
    /// <summary>
    /// The name of the agent associated with the tool request.
    /// </summary>
    public string AgentName { get; }

    /// <summary>
    /// A list of approval responses.
    /// </summary>
    public IList<AIContent> InputResponses { get; }

    [JsonConstructor]
    internal UserInputResponse(string agentName, IList<AIContent> inputResponses)
    {
        this.AgentName = agentName;
        this.InputResponses = inputResponses;
    }

    /// <summary>
    /// Factory method to create an <see cref="UserInputResponse"/> from a <see cref="UserInputRequest"/>
    /// Ensures that all requests have a corresponding result.
    /// </summary>
    /// <param name="inputRequest">The input request.</param>
    /// <param name="inputResponses">One or more responses</param>
    /// <returns>An <see cref="UserInputResponse"/> that can be provided to the workflow.</returns>
    /// <exception cref="DeclarativeActionException">Not all <see cref="AgentFunctionToolRequest.FunctionCalls"/> have a corresponding <see cref="FunctionResultContent"/>.</exception>
    public static UserInputResponse Create(UserInputRequest inputRequest, params IEnumerable<UserInputResponseContent> inputResponses)
    {
        HashSet<string> callIds = [.. inputRequest.InputRequests.OfType<UserInputRequestContent>().Select(call => call.Id)];
        HashSet<string> resultIds = [.. inputResponses.Select(call => call.Id)];

        if (!callIds.SetEquals(resultIds))
        {
            throw new DeclarativeActionException($"Missing responses for: {string.Join(",", callIds.Except(resultIds))}");
        }

        return new UserInputResponse(inputRequest.AgentName, [.. inputResponses]);
    }
}
