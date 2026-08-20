// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Threading.Tasks;
using FluentAssertions;
using ModelContextProtocol.Server;

namespace Microsoft.Agents.AI.Mcp.UnitTests;

public class ListAgentToolsWithTasksTests
{
    [Fact]
    public async Task ListAgentToolsWithTasks_WrapsAllToolsAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("first", () => "first-result"),
            TestTools.Create("second", () => "second-result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);

        // Act
        var result = await fixture.Client.ListAgentToolsWithTasksAsync();

        // Assert
        result.Should().HaveCount(2);
        result.Should().AllBeOfType<TaskAwareMcpClientAIFunction>();
        result.Select(tool => tool.Name).Should().Equal("first", "second");
    }

    [Fact]
    public async Task ListAgentToolsWithTasks_ThrowsOnNullClientAsync()
    {
        // Arrange
        ModelContextProtocol.Client.McpClient client = null!;

        // Act
        Func<Task> act = async () => await client.ListAgentToolsWithTasksAsync();

        // Assert
        await act.Should().ThrowAsync<ArgumentNullException>();
    }

    [Fact]
    public async Task ListAgentToolsWithTasks_NonPositiveStuckPollLimit_ThrowsAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("tool", () => "result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        var options = new McpTaskOptions { MaxConsecutiveStuckPolls = 0 };

        // Act
        Func<Task> act = async () => await fixture.Client.ListAgentToolsWithTasksAsync(options);

        // Assert
        await act.Should().ThrowAsync<ArgumentOutOfRangeException>();
    }

    [Fact]
    public async Task ListAgentToolsWithTasks_NonPositiveInputRequestLimit_ThrowsAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("tool", () => "result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        var options = new McpTaskOptions { MaxTotalInputRequests = 0 };

        // Act
        Func<Task> act = async () => await fixture.Client.ListAgentToolsWithTasksAsync(options);

        // Assert
        await act.Should().ThrowAsync<ArgumentOutOfRangeException>();
    }

    [Fact]
    public async Task ListAgentToolsWithTasks_NonPositiveCancellationTimeout_ThrowsAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("tool", () => "result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        var options = new McpTaskOptions { RemoteCancellationTimeout = TimeSpan.Zero };

        // Act
        Func<Task> act = async () => await fixture.Client.ListAgentToolsWithTasksAsync(options);

        // Assert
        await act.Should().ThrowAsync<ArgumentOutOfRangeException>();
    }

    [Fact]
    public async Task ListAgentToolsWithTasks_SubMillisecondCancellationTimeout_ThrowsAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("tool", () => "result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        var options = new McpTaskOptions { RemoteCancellationTimeout = TimeSpan.FromTicks(1) };

        // Act
        Func<Task> act = async () => await fixture.Client.ListAgentToolsWithTasksAsync(options);

        // Assert
        await act.Should().ThrowAsync<ArgumentOutOfRangeException>();
    }

    [Fact]
    public async Task ListAgentToolsWithTasks_InvalidPollingIntervalRange_ThrowsAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("tool", () => "result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        var options = new McpTaskOptions
        {
            MinimumPollingInterval = TimeSpan.FromMilliseconds(20),
            MaximumPollingInterval = TimeSpan.FromMilliseconds(10),
        };

        // Act
        Func<Task> act = async () => await fixture.Client.ListAgentToolsWithTasksAsync(options);

        // Assert
        await act.Should().ThrowAsync<ArgumentOutOfRangeException>();
    }

    [Fact]
    public async Task ListAgentToolsWithTasks_PollingRangeWithoutWholeMillisecond_ThrowsAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("tool", () => "result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        var options = new McpTaskOptions
        {
            MinimumPollingInterval = TimeSpan.FromTicks(1),
            MaximumPollingInterval = TimeSpan.FromTicks(TimeSpan.TicksPerMillisecond - 1),
        };

        // Act
        Func<Task> act = async () => await fixture.Client.ListAgentToolsWithTasksAsync(options);

        // Assert
        await act.Should().ThrowAsync<ArgumentOutOfRangeException>();
    }

    [Fact]
    public async Task ListAgentToolsWithTasks_PollingMaximumAboveRuntimeLimit_ThrowsAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("tool", () => "result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        var options = new McpTaskOptions
        {
            MaximumPollingInterval = TimeSpan.FromMilliseconds(uint.MaxValue),
        };

        // Act
        Func<Task> act = async () => await fixture.Client.ListAgentToolsWithTasksAsync(options);

        // Assert
        await act.Should().ThrowAsync<ArgumentOutOfRangeException>();
    }
}
