// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using ModelContextProtocol.Server;

namespace Agent_Step10_AsMcpTool;

/// <summary>
/// Contains extension methods for <see cref="AIAgent"/>.
/// </summary>
internal static class AIAgentExtensions
{
    /// <summary>
    /// Exposes an <see cref="AIAgent"/> as a <see cref="McpServerTool"/> that can be registered with an MCP server.
    /// </summary>
    /// <param name="agent">The agent to expose as an MCP tool.</param>
    /// <param name="title">A human-readable title for the tool that can be displayed to users. If not provided, the tool name or agent name will be used.</param>
    /// <param name="name">The tool name to use. If not provided, the agent's name will be used.</param>
    /// <param name="description">The tool description to use. If not provided, the agent's description will be used.</param>
    /// <returns>The <see cref="McpServerTool"/> that wraps the agent.</returns>
    public static McpServerTool AsMcpTool(this AIAgent agent, string? title = null, string? name = null, string? description = null)
    {
        async Task<string> RunAgentAsync(
            [Description("Available information that will guide in performing this operation.")] string query,
            CancellationToken cancellationToken = default)
        {
            AgentRunResponse response = await agent.RunAsync(query, cancellationToken: cancellationToken);

            return response.ToString();
        }

        return McpServerTool.Create(RunAgentAsync, new McpServerToolCreateOptions()
        {
            Title = title ?? name ?? agent.Name,
            Name = name ?? agent.Name,
            Description = description ?? agent.Description
        });
    }
}
