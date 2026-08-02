// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Mcp;

/// <summary>
/// Extension methods on <see cref="McpClient"/> that expose MCP server tools to a Microsoft
/// Agent Framework agent with optional long-running task (SEP-2663) handling.
/// </summary>
public static class McpClientTaskExtensions
{
    /// <summary>
    /// Lists tools advertised by the connected MCP server and returns each as an
    /// <see cref="AIFunction"/>. Tools that declare <see cref="ToolTaskSupport.Required"/>
    /// are wrapped with task-aware behavior so an agent can transparently drive long-running
    /// invocations. All other tools — including those that declare
    /// <see cref="ToolTaskSupport.Optional"/> — are returned as-is, preserving inline
    /// (synchronous) invocation semantics by default.
    /// </summary>
    /// <param name="client">The connected MCP client.</param>
    /// <param name="options">
    /// Options that control the task lifecycle for task-capable tools.
    /// When <see langword="null"/>, defaults described on <see cref="McpTaskOptions"/> apply.
    /// </param>
    /// <param name="cancellationToken">Token used to cancel listing the server's tools.</param>
    /// <returns>The tools, ready to pass to <c>AsAIAgent(tools: …)</c>.</returns>
    public static async Task<IReadOnlyList<AIFunction>> ListAgentToolsWithTaskSupportAsync(
        this McpClient client,
        McpTaskOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(client);

        McpTaskOptions effectiveOptions = options ?? new McpTaskOptions();

        IList<McpClientTool> tools = await client.ListToolsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);

        AIFunction[] result = new AIFunction[tools.Count];
        for (int i = 0; i < tools.Count; i++)
        {
            ToolTaskSupport? taskSupport = tools[i].ProtocolTool.Execution?.TaskSupport;
            if (taskSupport is ToolTaskSupport.Required)
            {
                result[i] = new TaskAwareMcpClientAIFunction(client, tools[i], effectiveOptions);
            }
            else
            {
                result[i] = tools[i];
            }
        }

        return result;
    }
}
