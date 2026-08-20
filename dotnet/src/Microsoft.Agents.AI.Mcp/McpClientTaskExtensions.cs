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
    private static readonly TimeSpan s_maximumSupportedDelay =
        TimeSpan.FromMilliseconds(uint.MaxValue - 1L);

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

        if (effectiveOptions.RemoteCancellationTimeout < TimeSpan.FromMilliseconds(1))
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                effectiveOptions.RemoteCancellationTimeout,
                "RemoteCancellationTimeout must be at least one millisecond.");
        }

        if (effectiveOptions.RemoteCancellationTimeout > s_maximumSupportedDelay)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                effectiveOptions.RemoteCancellationTimeout,
                $"RemoteCancellationTimeout must not exceed {s_maximumSupportedDelay.TotalMilliseconds} milliseconds.");
        }

        if (effectiveOptions.MinimumPollingInterval <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                effectiveOptions.MinimumPollingInterval,
                "MinimumPollingInterval must be greater than zero.");
        }

        if (effectiveOptions.MaximumPollingInterval < effectiveOptions.MinimumPollingInterval)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                effectiveOptions.MaximumPollingInterval,
                "MaximumPollingInterval must be greater than or equal to MinimumPollingInterval.");
        }

        if (effectiveOptions.MaximumPollingInterval > s_maximumSupportedDelay)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                effectiveOptions.MaximumPollingInterval,
                $"MaximumPollingInterval must not exceed {s_maximumSupportedDelay.TotalMilliseconds} milliseconds.");
        }

        long minimumPollingIntervalMs =
            (long)Math.Ceiling(effectiveOptions.MinimumPollingInterval.TotalMilliseconds);
        long maximumPollingIntervalMs =
            (long)Math.Floor(effectiveOptions.MaximumPollingInterval.TotalMilliseconds);
        if (minimumPollingIntervalMs > maximumPollingIntervalMs)
        {
            throw new ArgumentOutOfRangeException(
                nameof(options),
                effectiveOptions.MaximumPollingInterval,
                "The polling interval range must contain at least one whole millisecond value.");
        }

        // Snapshot mutable options before the asynchronous tool-list operation.
        effectiveOptions = new McpTaskOptions
        {
            CancelRemoteTaskOnLocalCancellation = effectiveOptions.CancelRemoteTaskOnLocalCancellation,
            MaxConsecutiveStuckPolls = effectiveOptions.MaxConsecutiveStuckPolls,
            MaxTotalInputRequests = effectiveOptions.MaxTotalInputRequests,
            RemoteCancellationTimeout = effectiveOptions.RemoteCancellationTimeout,
            MinimumPollingInterval = TimeSpan.FromMilliseconds(minimumPollingIntervalMs),
            MaximumPollingInterval = TimeSpan.FromMilliseconds(maximumPollingIntervalMs),
        };

        IList<McpClientTool> tools = await client.ListToolsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);

        AIFunction[] result = new AIFunction[tools.Count];
        for (int i = 0; i < tools.Count; i++)
        {
            result[i] = new TaskAwareMcpClientAIFunction(client, tools[i], effectiveOptions);
        }

        return result;
    }
}
