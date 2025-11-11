// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Local;

internal sealed class LocalAgentToolRegistry
{
    private readonly Dictionary<string, List<AITool>> _toolsByAgentName = new();

    public void AddTool(string agentName, AITool tool)
    {
        if (!this._toolsByAgentName.TryGetValue(agentName, out var tools))
        {
            tools = [];
            this._toolsByAgentName[agentName] = tools;
        }

        tools.Add(tool);
    }

    public IList<AITool> GetTools(string agentName)
    {
        return this._toolsByAgentName.TryGetValue(agentName, out var tools) ? tools : [];
    }
}
