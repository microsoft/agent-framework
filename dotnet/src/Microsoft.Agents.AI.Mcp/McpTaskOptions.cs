// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Mcp;

/// <summary>
/// Configures how task-aware MCP tools drive the
/// <see href="https://modelcontextprotocol.io/extensions/tasks/overview">MCP Tasks extension</see>
/// lifecycle.
/// </summary>
public sealed class McpTaskOptions
{
    /// <summary>
    /// Gets or sets the timeout for a best-effort <c>tasks/cancel</c> request.
    /// </summary>
    /// <value>The default is five seconds.</value>
    /// <remarks>
    /// The value must be at least one millisecond and must not exceed the maximum delay
    /// supported by the targeted .NET runtimes.
    /// </remarks>
    public TimeSpan RemoteCancellationTimeout { get; set; } = TimeSpan.FromSeconds(5);

    /// <summary>
    /// Gets or sets the minimum server-provided polling interval accepted by the client.
    /// </summary>
    /// <value>The default is 10 milliseconds.</value>
    /// <remarks>The value must be positive and not exceed <see cref="MaximumPollingInterval"/>.</remarks>
    public TimeSpan MinimumPollingInterval { get; set; } = TimeSpan.FromMilliseconds(10);

    /// <summary>
    /// Gets or sets the maximum server-provided polling interval accepted by the client.
    /// </summary>
    /// <value>The default is the maximum delay supported by the targeted .NET runtimes.</value>
    /// <remarks>
    /// The value must be at least <see cref="MinimumPollingInterval"/> and must not exceed
    /// 4,294,967,294 milliseconds.
    /// </remarks>
    public TimeSpan MaximumPollingInterval { get; set; } =
        TimeSpan.FromMilliseconds(uint.MaxValue - 1L);

    /// <summary>
    /// Gets or sets a value indicating whether local cancellation should send
    /// <c>tasks/cancel</c> for a task-backed invocation.
    /// </summary>
    /// <remarks>
    /// Defaults to <see langword="true"/>. Remote cancellation is best-effort and does not
    /// replace the original local cancellation if the server cannot be reached.
    /// </remarks>
    public bool CancelRemoteTaskOnLocalCancellation { get; set; } = true;

    /// <summary>
    /// Gets or sets the number of consecutive <c>input_required</c> polls without new input
    /// request keys allowed before the task is treated as stuck.
    /// </summary>
    /// <value>The default is 60.</value>
    /// <remarks>The value must be greater than zero.</remarks>
    public int MaxConsecutiveStuckPolls { get; set; } = 60;

    /// <summary>
    /// Gets or sets the maximum number of unique input requests a task may publish.
    /// </summary>
    /// <value>The default is 100.</value>
    /// <remarks>
    /// This per-task resource-safety limit bounds retained request keys and user or model
    /// interactions. The value must be greater than zero.
    /// </remarks>
    public int MaxTotalInputRequests { get; set; } = 100;
}
