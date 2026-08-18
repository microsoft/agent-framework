// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Mcp;

/// <summary>
/// Configures how an MCP client wrapper drives the
/// <see href="https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks">MCP tasks</see>
/// lifecycle when an underlying server tool returns a <c>CreateTaskResult</c>.
/// </summary>
/// <remarks>
/// <para>
/// All members of this type are subject to change. The MCP task surface is experimental
/// and tracks the in-flight specification.
/// </para>
/// </remarks>
public sealed class McpTaskOptions
{
    /// <summary>
    /// Gets or sets the time-to-live the wrapper attaches to a newly created server-side task.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/> the wrapper omits the <c>ttl</c> hint and lets the server
    /// pick its own value. The server's chosen TTL is always authoritative.
    /// </remarks>
    public TimeSpan? DefaultTimeToLive { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether the wrapper should send
    /// <c>tasks/cancel</c> when the local <see cref="System.Threading.CancellationToken"/>
    /// fires during a tool invocation.
    /// </summary>
    /// <remarks>
    /// Defaults to <see langword="true"/>: a local cancellation means "the caller is giving up
    /// on this tool invocation" and the server-side task has no further consumer.
    /// </remarks>
    public bool CancelRemoteTaskOnLocalCancellation { get; set; } = true;
}
