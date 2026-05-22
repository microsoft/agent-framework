// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;

namespace Microsoft.Agents.AI.Mcp.UnitTests;

public class ListAgentToolsWithTaskSupportTests
{
    [Fact]
    public async Task ListAgentToolsWithTaskSupport_WrapsTaskCapableTools_LeavesOthersAsIsAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("opt", ToolTaskSupport.Optional, () => "opt-result"),
            TestTools.Create("req", ToolTaskSupport.Required, () => "req-result"),
            TestTools.Create("forb", ToolTaskSupport.Forbidden, () => "forb-result"),
            TestTools.Create("none", taskSupport: null, () => "none-result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);

        // Act
        var result = await fixture.Client.ListAgentToolsWithTaskSupportAsync();

        // Assert
        result.Should().HaveCount(4);
        AIFunction opt = result.Single(f => f.Name == "opt");
        AIFunction req = result.Single(f => f.Name == "req");
        AIFunction forb = result.Single(f => f.Name == "forb");
        AIFunction none = result.Single(f => f.Name == "none");

        req.Should().BeOfType<TaskAwareMcpClientAIFunction>("Required tools must be wrapped");
        opt.Should().NotBeOfType<TaskAwareMcpClientAIFunction>("Optional tools must not be wrapped; inline invocation is preserved by default");
        forb.Should().NotBeOfType<TaskAwareMcpClientAIFunction>("Forbidden tools must not be wrapped");
        none.Should().NotBeOfType<TaskAwareMcpClientAIFunction>("Tools without execution metadata must not be wrapped");
    }

    [Fact]
    public async Task ListAgentToolsWithTaskSupport_ThrowsOnNullClientAsync()
    {
        // Arrange
        ModelContextProtocol.Client.McpClient client = null!;

        // Act
        Func<Task> act = async () => await client.ListAgentToolsWithTaskSupportAsync();

        // Assert
        await act.Should().ThrowAsync<ArgumentNullException>();
    }
}
