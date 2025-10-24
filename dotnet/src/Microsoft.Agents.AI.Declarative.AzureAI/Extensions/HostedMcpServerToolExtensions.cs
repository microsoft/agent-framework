// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Extension methods for <see cref="HostedMcpServerTool"/>.
/// </summary>
internal static class HostedMcpServerToolExtensions
{
    /// <summary>
    /// Creates a <see cref="MCPToolDefinition"/> from a <see cref="HostedMcpServerTool"/>.
    /// </summary>
    /// <param name="tool">Instance of <see cref="HostedMcpServerTool"/></param>
    internal static MCPToolDefinition CreateMcpToolDefinition(this HostedMcpServerTool tool)
    {
        Throw.IfNull(tool);
        Throw.IfNull(tool.ServerName);
        Throw.IfNull(tool.ServerAddress);

        var definition = new MCPToolDefinition(tool.ServerName, tool.ServerAddress);
        tool.AllowedTools?.ToList().ForEach(definition.AllowedTools.Add);
        return definition;
    }
}
