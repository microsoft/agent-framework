// Copyright (c) Microsoft. All rights reserved.

using System;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;

namespace Microsoft.Agents.AI.Mcp.UnitTests;

/// <summary>
/// Helpers to create <see cref="McpServerTool"/> instances with a specific
/// <see cref="ToolTaskSupport"/> level for in-memory fixtures.
/// </summary>
internal static class TestTools
{
    public static McpServerTool Create(string name, ToolTaskSupport? taskSupport, Delegate handler)
    {
        McpServerToolCreateOptions options = new()
        {
            Name = name,
            Description = $"Test tool {name}.",
        };

        if (taskSupport is ToolTaskSupport ts)
        {
            options.Execution = new ToolExecution { TaskSupport = ts };
        }

        return McpServerTool.Create(handler, options);
    }
}
