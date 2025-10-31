// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.AGUI.Shared;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.AGUI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AGUIAgent"/> class.
/// </summary>
public sealed class AGUIAgentTests
{
    [Fact]
    public async Task RunAsync_AggregatesStreamingUpdates_ReturnsCompleteMessagesAsync()
    {
        // Arrange
        using HttpClient httpClient = this.CreateMockHttpClient(new BaseEvent[]
        {
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageContentEvent { MessageId = "msg1", Delta = " World" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        });

        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, []);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        AgentRunResponse response = await agent.RunAsync(messages);

        // Assert
        Assert.NotNull(response);
        Assert.NotEmpty(response.Messages);
        ChatMessage message = response.Messages.First();
        Assert.Equal(ChatRole.Assistant, message.Role);
        Assert.Equal("Hello World", message.Text);
    }

    [Fact]
    public async Task RunAsync_WithEmptyUpdateStream_ContainsOnlyMetadataMessagesAsync()
    {
        // Arrange
        using HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, []);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        AgentRunResponse response = await agent.RunAsync(messages);

        // Assert
        Assert.NotNull(response);
        // RunStarted and RunFinished events are aggregated into messages by ToChatResponse()
        Assert.NotEmpty(response.Messages);
        Assert.All(response.Messages, m => Assert.Equal(ChatRole.Assistant, m.Role));
    }

    [Fact]
    public async Task RunAsync_WithNullMessages_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        using HttpClient httpClient = new();
        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, []);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => agent.RunAsync(messages: null!));
    }

    [Fact]
    public async Task RunAsync_WithNullThread_CreatesNewThreadAsync()
    {
        // Arrange
        using HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, []);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        AgentRunResponse response = await agent.RunAsync(messages, thread: null);

        // Assert
        Assert.NotNull(response);
    }

    [Fact]
    public async Task RunAsync_WithNonAGUIAgentThread_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        using HttpClient httpClient = new();
        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, []);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];
        AgentThread invalidThread = new TestInMemoryAgentThread();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync(messages, thread: invalidThread));
    }

    [Fact]
    public async Task RunStreamingAsync_YieldsAllEvents_FromServerStreamAsync()
    {
        // Arrange
        using HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, []);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages))
        {
            // Consume the stream
            updates.Add(update);
        }

        // Assert
        Assert.NotEmpty(updates);
        Assert.Contains(updates, u => u.ResponseId != null); // RunStarted sets ResponseId
        Assert.Contains(updates, u => u.Contents.Any(c => c is TextContent));
        Assert.Contains(updates, u => u.Contents.Count == 0 && u.ResponseId != null); // RunFinished has no text content
    }

    [Fact]
    public async Task RunStreamingAsync_WithNullMessages_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        using HttpClient httpClient = new();
        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, []);

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(async () =>
        {
            await foreach (var _ in agent.RunStreamingAsync(messages: null!))
            {
                // Intentionally empty - consuming stream to trigger exception
            }
        });
    }

    [Fact]
    public async Task RunStreamingAsync_WithNullThread_CreatesNewThreadAsync()
    {
        // Arrange
        using HttpClient httpClient = this.CreateMockHttpClient(new BaseEvent[]
        {
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        });

        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, []);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages, thread: null))
        {
            // Consume the stream
            updates.Add(update);
        }

        // Assert
        Assert.NotEmpty(updates);
    }

    [Fact]
    public async Task RunStreamingAsync_WithNonAGUIAgentThread_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        using HttpClient httpClient = new();
        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, []);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];
        AgentThread invalidThread = new TestInMemoryAgentThread();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in agent.RunStreamingAsync(messages, thread: invalidThread))
            {
                // Consume the stream
            }
        });
    }

    [Fact]
    public async Task RunStreamingAsync_GeneratesUniqueRunId_ForEachInvocationAsync()
    {
        // Arrange
        List<string> capturedRunIds = [];
        using HttpClient httpClient = this.CreateMockHttpClientWithCapture(new BaseEvent[]
        {
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        }, capturedRunIds);

        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, []);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        await foreach (var _ in agent.RunStreamingAsync(messages))
        {
            // Consume the stream
        }
        await foreach (var _ in agent.RunStreamingAsync(messages))
        {
            // Consume the stream
        }

        // Assert
        Assert.Equal(2, capturedRunIds.Count);
        Assert.NotEqual(capturedRunIds[0], capturedRunIds[1]);
    }

    [Fact]
    public async Task RunStreamingAsync_NotifiesThreadOfNewMessages_AfterCompletionAsync()
    {
        // Arrange
        using HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, []);
        AGUIAgentThread thread = new();
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];

        // Act
        await foreach (var _ in agent.RunStreamingAsync(messages, thread))
        {
            // Consume the stream
        }

        // Assert
        Assert.NotEmpty(thread.MessageStore);
    }

    [Fact]
    public void DeserializeThread_WithValidState_ReturnsAGUIAgentThread()
    {
        // Arrange
        using var httpClient = new HttpClient();
        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, []);
        AGUIAgentThread originalThread = new() { ThreadId = "test-thread-123" };
        JsonElement serialized = originalThread.Serialize();

        // Act
        AgentThread deserialized = agent.DeserializeThread(serialized);

        // Assert
        Assert.NotNull(deserialized);
        Assert.IsType<AGUIAgentThread>(deserialized);
        AGUIAgentThread typedThread = (AGUIAgentThread)deserialized;
        Assert.Equal("test-thread-123", typedThread.ThreadId);
    }

    private HttpClient CreateMockHttpClient(BaseEvent[] events)
    {
        string sseContent = string.Join("", events.Select(e =>
            $"data: {JsonSerializer.Serialize(e, AGUIJsonSerializerContext.Default.BaseEvent)}\n\n"));

        Mock<HttpMessageHandler> handlerMock = new();
        handlerMock
            .Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new HttpResponseMessage
            {
                StatusCode = HttpStatusCode.OK,
                Content = new StringContent(sseContent)
            });

        return new HttpClient(handlerMock.Object);
    }

    private HttpClient CreateMockHttpClientWithCapture(BaseEvent[] events, List<string> capturedRunIds)
    {
        string sseContent = string.Join("", events.Select(e =>
            $"data: {JsonSerializer.Serialize(e, AGUIJsonSerializerContext.Default.BaseEvent)}\n\n"));

        Mock<HttpMessageHandler> handlerMock = new();
        handlerMock
            .Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(async (HttpRequestMessage request, CancellationToken ct) =>
            {
#if NET
                string requestBody = await request.Content!.ReadAsStringAsync(ct).ConfigureAwait(false);
#else
                string requestBody = await request.Content!.ReadAsStringAsync().ConfigureAwait(false);
#endif
                RunAgentInput? input = JsonSerializer.Deserialize(requestBody, AGUIJsonSerializerContext.Default.RunAgentInput);
                if (input != null)
                {
                    capturedRunIds.Add(input.RunId);
                }

                return new HttpResponseMessage
                {
                    StatusCode = HttpStatusCode.OK,
                    Content = new StringContent(sseContent)
                };
            });

        return new HttpClient(handlerMock.Object);
    }

    private sealed class TestInMemoryAgentThread : InMemoryAgentThread
    {
    }

    [Fact]
    public async Task RunStreamingAsync_InvokesTools_WhenFunctionCallsReturnedAsync()
    {
        // Arrange
        bool toolInvoked = false;
        AIFunction testTool = AIFunctionFactory.Create(
            (string location) =>
            {
                toolInvoked = true;
                return $"Weather in {location}: Sunny, 72°F";
            },
            "GetWeather",
            "Gets the current weather for a location");

        using HttpClient httpClient = this.CreateMockHttpClientForToolCalls(
            firstResponse:
            [
                new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
                new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "GetWeather", ParentMessageId = "msg1" },
                new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{\"location\":\"Seattle\"}" },
                new ToolCallEndEvent { ToolCallId = "call_1" },
                new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
            ],
            secondResponse:
            [
                new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
                new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
                new TextMessageContentEvent { MessageId = "msg2", Delta = "The weather is nice!" },
                new TextMessageEndEvent { MessageId = "msg2" },
                new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
            ]);

        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, [testTool]);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "What's the weather?")];

        // Act
        List<AgentRunResponseUpdate> allUpdates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages))
        {
            allUpdates.Add(update);
        }

        // Assert
        Assert.True(toolInvoked, "Tool should have been invoked");
        Assert.NotEmpty(allUpdates);
        // Should have updates from both the tool call and the final response
        Assert.Contains(allUpdates, u => u.Contents.Any(c => c is FunctionCallContent));
        Assert.Contains(allUpdates, u => u.Contents.Any(c => c is TextContent));
    }

    [Fact]
    public async Task RunStreamingAsync_DoesNotInvokeTools_WhenSomeToolsNotAvailableAsync()
    {
        // Arrange
        bool tool1Invoked = false;
        AIFunction tool1 = AIFunctionFactory.Create(
            () => { tool1Invoked = true; return "Result1"; },
            "Tool1");

        using HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "Tool1", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "call_1" },
            new ToolCallStartEvent { ToolCallId = "call_2", ToolCallName = "Tool2", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_2", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "call_2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, [tool1]); // Only tool1, not tool2
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<AgentRunResponseUpdate> allUpdates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages))
        {
            allUpdates.Add(update);
        }

        // Assert
        Assert.False(tool1Invoked, "Tool1 should NOT be invoked because Tool2 is not available");
        // Should return the function calls to the caller without invoking
        Assert.Contains(allUpdates, u => u.Contents.Any(c => c is FunctionCallContent fc && fc.Name == "Tool1"));
        Assert.Contains(allUpdates, u => u.Contents.Any(c => c is FunctionCallContent fc && fc.Name == "Tool2"));
    }

    [Fact]
    public async Task RunStreamingAsync_HandlesToolInvocationErrors_GracefullyAsync()
    {
        // Arrange
        AIFunction faultyTool = AIFunctionFactory.Create(
            () =>
            {
                throw new InvalidOperationException("Tool failed!");
#pragma warning disable CS0162 // Unreachable code detected
                return string.Empty;
#pragma warning restore CS0162 // Unreachable code detected
            },
            "FaultyTool");

        using HttpClient httpClient = this.CreateMockHttpClientForToolCalls(
            firstResponse:
            [
                new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
                new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "FaultyTool", ParentMessageId = "msg1" },
                new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{}" },
                new ToolCallEndEvent { ToolCallId = "call_1" },
                new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
            ],
            secondResponse:
            [
                new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
                new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
                new TextMessageContentEvent { MessageId = "msg2", Delta = "I encountered an error." },
                new TextMessageEndEvent { MessageId = "msg2" },
                new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
            ]);

        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, [faultyTool]);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<AgentRunResponseUpdate> allUpdates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages))
        {
            allUpdates.Add(update);
        }

        // Assert - should complete without throwing
        Assert.NotEmpty(allUpdates);
    }

    [Fact]
    public async Task RunStreamingAsync_InvokesMultipleTools_InSingleTurnAsync()
    {
        // Arrange
        int tool1CallCount = 0;
        int tool2CallCount = 0;
        AIFunction tool1 = AIFunctionFactory.Create(() => { tool1CallCount++; return "Result1"; }, "Tool1");
        AIFunction tool2 = AIFunctionFactory.Create(() => { tool2CallCount++; return "Result2"; }, "Tool2");

        using HttpClient httpClient = this.CreateMockHttpClientForToolCalls(
            firstResponse:
            [
                new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
                new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "Tool1", ParentMessageId = "msg1" },
                new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{}" },
                new ToolCallEndEvent { ToolCallId = "call_1" },
                new ToolCallStartEvent { ToolCallId = "call_2", ToolCallName = "Tool2", ParentMessageId = "msg1" },
                new ToolCallArgsEvent { ToolCallId = "call_2", Delta = "{}" },
                new ToolCallEndEvent { ToolCallId = "call_2" },
                new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
            ],
            secondResponse:
            [
                new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
                new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
                new TextMessageContentEvent { MessageId = "msg2", Delta = "Done" },
                new TextMessageEndEvent { MessageId = "msg2" },
                new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
            ]);

        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, [tool1, tool2]);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        await foreach (var _ in agent.RunStreamingAsync(messages))
        {
        }

        // Assert
        Assert.Equal(1, tool1CallCount);
        Assert.Equal(1, tool2CallCount);
    }

    [Fact]
    public async Task RunStreamingAsync_UpdatesThreadWithToolMessages_AfterCompletionAsync()
    {
        // Arrange
        AIFunction testTool = AIFunctionFactory.Create(() => "Result", "TestTool");

        using HttpClient httpClient = this.CreateMockHttpClientForToolCalls(
            firstResponse:
            [
                new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
                new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "TestTool", ParentMessageId = "msg1" },
                new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{}" },
                new ToolCallEndEvent { ToolCallId = "call_1" },
                new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
            ],
            secondResponse:
            [
                new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
                new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
                new TextMessageContentEvent { MessageId = "msg2", Delta = "Complete" },
                new TextMessageEndEvent { MessageId = "msg2" },
                new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
            ]);

        AGUIAgent agent = new("agent1", "Test agent", httpClient, "http://localhost/agent", AGUIJsonSerializerContext.Default.Options, [testTool]);
        AGUIAgentThread thread = new();
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        await foreach (var _ in agent.RunStreamingAsync(messages, thread))
        {
        }

        // Assert
        Assert.NotEmpty(thread.MessageStore);
        // Should contain: original user message, assistant message with function call, tool result, final assistant message
        Assert.Contains(thread.MessageStore, m => m.Role == ChatRole.User);
        Assert.Contains(thread.MessageStore, m => m.Role == ChatRole.Assistant);
        Assert.Contains(thread.MessageStore, m => m.Role == ChatRole.Tool);
    }

    private HttpClient CreateMockHttpClientForToolCalls(BaseEvent[] firstResponse, BaseEvent[] secondResponse)
    {
        int callCount = 0;
        Mock<HttpMessageHandler> handlerMock = new();
        handlerMock
            .Protected()
            .Setup<Task<HttpResponseMessage>>(
                "SendAsync",
                ItExpr.IsAny<HttpRequestMessage>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(() =>
            {
                callCount++;
                BaseEvent[] events = callCount == 1 ? firstResponse : secondResponse;
                string sseContent = string.Join("", events.Select(e =>
                    $"data: {JsonSerializer.Serialize(e, AGUIJsonSerializerContext.Default.BaseEvent)}\n\n"));

                return Task.FromResult(new HttpResponseMessage
                {
                    StatusCode = HttpStatusCode.OK,
                    Content = new StringContent(sseContent)
                });
            });

        return new HttpClient(handlerMock.Object);
    }
}
