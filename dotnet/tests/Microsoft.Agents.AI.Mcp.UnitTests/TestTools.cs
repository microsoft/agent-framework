// Copyright (c) Microsoft. All rights reserved.

using System;
using ModelContextProtocol.Server;

namespace Microsoft.Agents.AI.Mcp.UnitTests;

/// <summary>
/// Helpers to create <see cref="McpServerTool"/> instances for in-memory fixtures.
/// </summary>
internal static class TestTools
{
    public static McpServerTool Create(string name, Delegate handler) =>
        McpServerTool.Create(
            handler,
            new McpServerToolCreateOptions
            {
                Name = name,
                Description = $"Test tool {name}.",
            });
}
