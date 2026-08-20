// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Mcp;

/// <summary>
/// Configures how task-aware MCP tools drive the
/// <see href="https://modelcontextprotocol.io/extensions/tasks/overview">MCP Tasks extension</see>
/// lifecycle.
/// </summary>
public sealed class McpTaskOptions
{
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
}
