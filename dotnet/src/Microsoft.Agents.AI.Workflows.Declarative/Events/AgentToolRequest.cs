// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Events;

/// <summary>
/// Represents a request for user input.
/// </summary>
public sealed class AgentToolRequest
{
    /// <summary>
    /// %%% COMMENT
    /// </summary>
    public string AgentName { get; }

    /// <summary>
    /// %%% COMMENT
    /// </summary>
    public IReadOnlyList<FunctionCallContent> FunctionCalls { get; }

    internal AgentToolRequest(string agentName, IEnumerable<FunctionCallContent> functionCalls)
    {
        this.AgentName = agentName;
        this.FunctionCalls = functionCalls.ToImmutableArray();
    }
}
