// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Represents a hosted MCP server tool that can be specified to an AI service.
/// </summary>
public class HostedMcpServerTool : AITool
{
    /// <summary>
    /// Initializes a new instance of the <see cref="HostedMcpServerTool"/> class.
    /// </summary>
    /// <param name="serverName">The name of the remote MCP server.</param>
    /// <param name="url">The URL of the remote MCP server.</param>
    public HostedMcpServerTool(string serverName, Uri url)
    {
        ServerName = Throw.IfNullOrWhitespace(serverName);
        Url = Throw.IfNull(url);
    }

    /// <summary>
    /// Gets the name of the remote MCP server that is used to identify it.
    /// </summary>
    public string ServerName { get; }

    /// <summary>
    /// Gets the URL of the remote MCP server.
    /// </summary>
    public Uri Url { get; }

    /// <summary>
    /// Gets or sets the description of the remote MCP server, used to provide more context to the AI service.
    /// </summary>
    public string? ServerDescription { get; set; }

    /// <summary>
    /// Gets or sets the list of tools allowed to be used by the AI service.
    /// </summary>
    public IList<string>? AllowedTools { get; set; }

    /// <summary>
    /// Gets or sets the approval mode that indicates when the AI service should require user approval for tool calls to the remote MCP server.
    /// </summary>
    /// <remarks>
    /// You can set this property to <see cref="HostedMcpServerToolApprovalMode.AlwaysRequire"/> to require approval for all tool calls,
    /// or to <see cref="HostedMcpServerToolApprovalMode.NeverRequire"/> to never require approval.
    /// </remarks>
    public HostedMcpServerToolApprovalMode? ApprovalMode { get; set; }

    /// <summary>
    /// Gets or sets the HTTP headers that the AI service should use when making tool calls to the remote MCP server.
    /// </summary>
    /// <remarks>
    /// This property is useful for specifying the authentication header or other headers required by the MCP server.
    /// </remarks>
    public IDictionary<string, string>? Headers { get; set; }
}
