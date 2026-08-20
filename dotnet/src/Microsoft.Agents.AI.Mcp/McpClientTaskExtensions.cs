// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI.Mcp;

/// <summary>
/// Extension methods on <see cref="McpClient"/> that expose MCP server tools to a Microsoft
/// Agent Framework agent with transparent MCP Tasks extension handling.
/// </summary>
public static class McpClientTaskExtensions
{
    /// <summary>
    /// Lists tools advertised by the connected MCP server and returns each as an
    /// <see cref="AIFunction"/> that opts into the
    /// <see href="https://modelcontextprotocol.io/extensions/tasks/overview">MCP Tasks extension</see>.
    /// The returned functions transparently poll task-backed calls to completion and also accept
    /// ordinary inline results from servers that do not create a task.
    /// </summary>
    /// <param name="client">The connected MCP client.</param>
    /// <param name="options">
    /// Options that control the task lifecycle. When <see langword="null"/>, defaults described
    /// on <see cref="McpTaskOptions"/> apply.
    /// </param>
    /// <param name="cancellationToken">Token used to cancel listing the server's tools.</param>
    /// <returns>The tools, ready to pass to <c>AsAIAgent(tools: …)</c>.</returns>
    /// <exception cref="ArgumentOutOfRangeException">
    /// <paramref name="options"/> specifies a non-positive lifecycle limit.
    /// </exception>
    public static async Task<IReadOnlyList<AIFunction>> ListAgentToolsWithTasksAsync(
        this McpClient client,
        McpTaskOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        _ = Throw.IfNull(client);

        McpTaskOptions effectiveOptions = options ?? new();
        if (effectiveOptions.MaxConsecutiveStuckPolls <= 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                effectiveOptions.MaxConsecutiveStuckPolls,
                "MaxConsecutiveStuckPolls must be greater than zero.");
        }

        if (effectiveOptions.MaxTotalInputRequests <= 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                effectiveOptions.MaxTotalInputRequests,
                "MaxTotalInputRequests must be greater than zero.");
        }

        IList<McpClientTool> tools = await client.ListToolsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);

        AIFunction[] result = new AIFunction[tools.Count];
        for (int i = 0; i < tools.Count; i++)
        {
            result[i] = new TaskAwareMcpClientAIFunction(client, tools[i], effectiveOptions);
        }

        return result;
    }
}
