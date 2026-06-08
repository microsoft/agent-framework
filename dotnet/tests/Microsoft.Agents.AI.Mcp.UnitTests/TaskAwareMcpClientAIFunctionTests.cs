// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;

namespace Microsoft.Agents.AI.Mcp.UnitTests;

public class TaskAwareMcpClientAIFunctionTests
{
    [Fact]
    public async Task InvokeAsync_RequiredTool_HappyPath_ReturnsResultAsync()
    {
        // Arrange
        McpServerPrimitiveCollection<McpServerTool> tools = [
            TestTools.Create("req", ToolTaskSupport.Required, () => "required-result"),
        ];
        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        var result = await fixture.Client.ListAgentToolsWithTaskSupportAsync();
        AIFunction req = result.Single(f => f.Name == "req");
        req.Should().BeOfType<TaskAwareMcpClientAIFunction>();

        // Act
        object? invokeResult = await req.InvokeAsync(arguments: null, CancellationToken.None);

        // Assert
        JsonElement payload = invokeResult.Should().BeOfType<JsonElement>().Subject;
        ExtractTextContent(payload).Should().Be("required-result");
    }

    [Fact]
    public async Task InvokeAsync_PropagatesDefaultTimeToLiveAsync()
    {
        // Arrange — capture the request meta on the server so we can assert TTL flowed through.
        TimeSpan? observedTtl = null;
        McpServerTool tool = McpServerTool.Create(
            (RequestContext<CallToolRequestParams> ctx) =>
            {
                observedTtl = ctx.Params?.Task?.TimeToLive;
                return "ok";
            },
            new McpServerToolCreateOptions
            {
                Name = "ttl-tool",
                Description = "Echoes the requested TTL.",
                Execution = new ToolExecution { TaskSupport = ToolTaskSupport.Required },
            });
        McpServerPrimitiveCollection<McpServerTool> tools = [tool];

        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);

        TimeSpan requestedTtl = TimeSpan.FromMinutes(7);
        var result = await fixture.Client.ListAgentToolsWithTaskSupportAsync(new McpTaskOptions { DefaultTimeToLive = requestedTtl });
        AIFunction wrapped = result.Single();

        // Act
        _ = await wrapped.InvokeAsync(arguments: null, CancellationToken.None);

        // Assert
        observedTtl.Should().Be(requestedTtl);
    }

    [Fact]
    public async Task InvokeAsync_RespectsCancellationAsync()
    {
        // Arrange — a tool that never completes until it's cancelled.
        var serverCancelled = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        McpServerTool tool = McpServerTool.Create(
            async (CancellationToken ct) =>
            {
                try
                {
                    await Task.Delay(Timeout.Infinite, ct);
                }
                catch (OperationCanceledException)
                {
                    serverCancelled.TrySetResult(true);
                    throw;
                }

                return "should-not-complete";
            },
            new McpServerToolCreateOptions
            {
                Name = "blocking",
                Description = "Blocks indefinitely until cancelled.",
                Execution = new ToolExecution { TaskSupport = ToolTaskSupport.Required },
            });
        McpServerPrimitiveCollection<McpServerTool> tools = [tool];

        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        var result = await fixture.Client.ListAgentToolsWithTaskSupportAsync();
        AIFunction wrapped = result.Single();

        using CancellationTokenSource cts = new();

        // Act — start the invocation, cancel after a brief delay.
        Task<object?> invocation = wrapped.InvokeAsync(arguments: null, cts.Token).AsTask();
        await Task.Delay(200);
        cts.Cancel();

        // Assert — wrapper observes cancellation and signals server-side cancellation.
        Func<Task> awaitInvocation = async () => await invocation;
        await awaitInvocation.Should().ThrowAsync<OperationCanceledException>();

        // Server-side handler should have observed cancellation as a result of the wrapper's
        // tasks/cancel call (best-effort wait — give the server-loop a few seconds).
        Task observedTask = serverCancelled.Task;
        Task completed = await Task.WhenAny(observedTask, Task.Delay(TimeSpan.FromSeconds(5)));
        completed.Should().BeSameAs(observedTask, "the wrapper should have issued tasks/cancel");
    }

    [Fact]
    public async Task InvokeAsync_FailedTask_ThrowsInvalidOperationAsync()
    {
        // Arrange — a tool whose handler throws, which the server surfaces as a Failed task.
        McpServerTool tool = McpServerTool.Create(
            (Func<string>)(() => throw new InvalidOperationException("simulated tool failure")),
            new McpServerToolCreateOptions
            {
                Name = "boom",
                Description = "Throws unconditionally.",
                Execution = new ToolExecution { TaskSupport = ToolTaskSupport.Required },
            });
        McpServerPrimitiveCollection<McpServerTool> tools = [tool];

        await using InMemoryMcpServerFixture fixture = await InMemoryMcpServerFixture.CreateAsync(tools);
        var result = await fixture.Client.ListAgentToolsWithTaskSupportAsync();
        AIFunction wrapped = result.Single();

        // Act
        Func<Task> act = async () => await wrapped.InvokeAsync(arguments: null, CancellationToken.None);

        // Assert — Phase 1 surfaces non-Completed terminal states as InvalidOperationException
        // carrying the server's StatusMessage. (See PollAndRetrieveResultAsync.)
        await act.Should().ThrowAsync<Exception>().Where(ex =>
            ex is InvalidOperationException
            || ex.GetType().FullName == "ModelContextProtocol.McpException");
    }

    /// <summary>
    /// Extracts the first text-content block from a serialized <c>CallToolResult</c>
    /// (the JSON shape returned by the wrapper and by <c>McpClientTool.InvokeAsync</c>).
    /// </summary>
    private static string ExtractTextContent(JsonElement payload)
    {
        payload.ValueKind.Should().Be(JsonValueKind.Object);
        JsonElement content = payload.GetProperty("content");
        content.ValueKind.Should().Be(JsonValueKind.Array);
        JsonElement firstBlock = content.EnumerateArray().First();
        return firstBlock.GetProperty("text").GetString()!;
    }
}
