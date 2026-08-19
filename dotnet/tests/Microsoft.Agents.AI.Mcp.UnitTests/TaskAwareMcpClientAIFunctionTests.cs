// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;

namespace Microsoft.Agents.AI.Mcp.UnitTests;

public class TaskAwareMcpClientAIFunctionTests
{
    [Fact]
    public async Task InvokeAsync_TaskBackedTool_ReturnsResultAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("task-tool", async () =>
            {
                await Task.Delay(25);
                return "task-result";
            }),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        AIFunction wrapped = (await fixture.Client.ListAgentToolsWithTasksAsync()).Single();

        // Act
        object? result = await wrapped.InvokeAsync(arguments: null, CancellationToken.None);

        // Assert
        result.Should().BeOfType<TextContent>()
            .Which.Text.Should().Be("task-result");
        fixture.CreatedTaskCount.Should().Be(1);
    }

    [Fact]
    public async Task InvokeAsync_ServerWithoutTasks_ReturnsInlineResultAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("inline-tool", () => "inline-result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools, enableTasks: false);
        AIFunction wrapped = (await fixture.Client.ListAgentToolsWithTasksAsync()).Single();

        // Act
        object? result = await wrapped.InvokeAsync(arguments: null, CancellationToken.None);

        // Assert
        result.Should().BeOfType<TextContent>()
            .Which.Text.Should().Be("inline-result");
        fixture.CreatedTaskCount.Should().Be(0);
    }

    [Fact]
    public async Task InvokeAsync_InputRequired_DispatchesClientHandlerAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            McpServerTool.Create(
                async (McpServer server, CancellationToken cancellationToken) =>
                {
                    ElicitResult elicitation = await server.ElicitAsync(
                        new ElicitRequestParams
                        {
                            Message = "Confirm the operation.",
                            RequestedSchema = new(),
                        },
                        cancellationToken);

                    return $"{elicitation.Action}:{elicitation.Content!["confirmed"].GetString()}";
                },
                new McpServerToolCreateOptions
                {
                    Name = "input-tool",
                    Description = "Requests confirmation before completing.",
                }),
        ];
        var clientOptions = new McpClientOptions();
        clientOptions.Handlers.ElicitationHandler = (_, _) =>
            new ValueTask<ElicitResult>(
                new ElicitResult
                {
                    Action = "accept",
                    Content = new Dictionary<string, JsonElement>
                    {
                        ["confirmed"] = JsonSerializer.SerializeToElement("yes"),
                    },
                });
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(
            tools,
            clientOptions: clientOptions);
        AIFunction wrapped = (await fixture.Client.ListAgentToolsWithTasksAsync()).Single();

        // Act
        object? result = await wrapped.InvokeAsync(arguments: null, CancellationToken.None);

        // Assert
        result.Should().BeOfType<TextContent>()
            .Which.Text.Should().Be("accept:yes");
        fixture.CreatedTaskCount.Should().Be(1);
        fixture.InputRequestCount.Should().Be(1);
    }

    [Fact]
    public async Task InvokeAsync_ForwardsNullPrimitiveAndComplexArgumentsAsync()
    {
        // Arrange
        IDictionary<string, JsonElement>? observedArguments = null;
        McpServerPrimitiveCollection<McpServerTool> tools = [
            McpServerTool.Create(
                (RequestContext<CallToolRequestParams> context) =>
                {
                    observedArguments = context.Params?.Arguments;
                    return "ok";
                },
                new McpServerToolCreateOptions
                {
                    Name = "arguments-tool",
                    Description = "Captures arguments.",
                }),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        AIFunction wrapped = (await fixture.Client.ListAgentToolsWithTasksAsync()).Single();
        var arguments = new AIFunctionArguments
        {
            ["optional"] = null,
            ["count"] = 3,
            ["payload"] = new Dictionary<string, object?> { ["label"] = "nested" },
        };

        // Act
        _ = await wrapped.InvokeAsync(arguments, CancellationToken.None);

        // Assert
        observedArguments.Should().NotBeNull();
        observedArguments!["optional"].ValueKind.Should().Be(JsonValueKind.Null);
        observedArguments["count"].GetInt32().Should().Be(3);
        observedArguments["payload"].GetProperty("label").GetString().Should().Be("nested");
    }

    [Fact]
    public async Task InvokeAsync_SimpleResult_MatchesMcpClientToolProjectionAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("projection-tool", () => "projected-result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        McpClientTool inner = (await fixture.Client.ListToolsAsync()).Single();
        AIFunction wrapped = (await fixture.Client.ListAgentToolsWithTasksAsync()).Single();

        // Act
        object? innerResult = await inner.InvokeAsync(arguments: null, CancellationToken.None);
        object? wrappedResult = await wrapped.InvokeAsync(arguments: null, CancellationToken.None);

        // Assert
        wrappedResult.Should().BeEquivalentTo(innerResult);
    }

    [Fact]
    public async Task InvokeAsync_ToolError_PreservesCallToolResultEnvelopeAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create(
                "error-tool",
                () => new CallToolResult
                {
                    IsError = true,
                    Content = [new TextContentBlock { Text = "tool failed" }],
                }),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        AIFunction wrapped = (await fixture.Client.ListAgentToolsWithTasksAsync()).Single();

        // Act
        object? result = await wrapped.InvokeAsync(arguments: null, CancellationToken.None);

        // Assert
        JsonElement payload = result.Should().BeOfType<JsonElement>().Subject;
        payload.GetProperty("isError").GetBoolean().Should().BeTrue();
        payload.GetProperty("content")[0].GetProperty("text").GetString().Should().Be("tool failed");
    }

    [Fact]
    public async Task InvokeAsync_LocalCancellation_CancelsPollingAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create(
                "blocking-tool",
                async (CancellationToken cancellationToken) =>
                {
                    await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
                    return "unreachable";
                }),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        AIFunction wrapped = (await fixture.Client.ListAgentToolsWithTasksAsync()).Single();
        using var cts = new CancellationTokenSource(TimeSpan.FromMilliseconds(100));

        // Act
        Func<Task> act = async () => await wrapped.InvokeAsync(arguments: null, cts.Token);

        // Assert
        await act.Should().ThrowAsync<OperationCanceledException>();
    }
}
