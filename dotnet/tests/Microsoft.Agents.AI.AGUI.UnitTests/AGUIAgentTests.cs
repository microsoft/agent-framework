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
        HttpClient httpClient = this.CreateMockHttpClient(new BaseEvent[]
        {
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageContentEvent { MessageId = "msg1", Delta = " World" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        });

        AGUIAgent agent = new("agent1", "Test agent", [], httpClient, "http://localhost/agent");
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
        HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        AGUIAgent agent = new("agent1", "Test agent", [], httpClient, "http://localhost/agent");
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        AgentRunResponse response = await agent.RunAsync(messages);

        // Assert
        Assert.NotNull(response);
        // RunStarted and RunFinished events are aggregated into messages by ToChatResponse()
        // So the response will contain metadata messages (RunStartedContent, RunFinishedContent)
        Assert.NotEmpty(response.Messages);
        Assert.All(response.Messages, m => Assert.Equal(ChatRole.Assistant, m.Role));
    }

    [Fact]
    public async Task RunAsync_WithNullMessages_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        HttpClient httpClient = new();
        AGUIAgent agent = new("agent1", "Test agent", [], httpClient, "http://localhost/agent");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() => agent.RunAsync(messages: null!));
    }

    [Fact]
    public async Task RunAsync_WithNullThread_CreatesNewThreadAsync()
    {
        // Arrange
        HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        AGUIAgent agent = new("agent1", "Test agent", [], httpClient, "http://localhost/agent");
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
        HttpClient httpClient = new();
        AGUIAgent agent = new("agent1", "Test agent", [], httpClient, "http://localhost/agent");
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];
        AgentThread invalidThread = new TestInMemoryAgentThread();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => agent.RunAsync(messages, thread: invalidThread));
    }

    [Fact]
    public async Task RunStreamingAsync_YieldsAllEvents_FromServerStreamAsync()
    {
        // Arrange
        HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        AGUIAgent agent = new("agent1", "Test agent", [], httpClient, "http://localhost/agent");
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages))
        {
            updates.Add(update);
        }

        // Assert
        Assert.NotEmpty(updates);
        Assert.Contains(updates, u => u.Contents.Any(c => c is RunStartedContent));
        Assert.Contains(updates, u => u.Contents.Any(c => c is TextContent));
        Assert.Contains(updates, u => u.Contents.Any(c => c is RunFinishedContent));
    }

    [Fact]
    public async Task RunStreamingAsync_WithNullMessages_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        HttpClient httpClient = new();
        AGUIAgent agent = new("agent1", "Test agent", [], httpClient, "http://localhost/agent");

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(async () =>
        {
            await foreach (var _ in agent.RunStreamingAsync(messages: null!))
            {
            }
        });
    }

    [Fact]
    public async Task RunStreamingAsync_WithNullThread_CreatesNewThreadAsync()
    {
        // Arrange
        HttpClient httpClient = this.CreateMockHttpClient(new BaseEvent[]
        {
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        });

        AGUIAgent agent = new("agent1", "Test agent", [], httpClient, "http://localhost/agent");
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages, thread: null))
        {
            updates.Add(update);
        }

        // Assert
        Assert.NotEmpty(updates);
    }

    [Fact]
    public async Task RunStreamingAsync_WithNonAGUIAgentThread_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        HttpClient httpClient = new();
        AGUIAgent agent = new("agent1", "Test agent", [], httpClient, "http://localhost/agent");
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];
        AgentThread invalidThread = new TestInMemoryAgentThread();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in agent.RunStreamingAsync(messages, thread: invalidThread))
            {
            }
        });
    }

    [Fact]
    public async Task RunStreamingAsync_GeneratesUniqueRunId_ForEachInvocationAsync()
    {
        // Arrange
        List<string> capturedRunIds = [];
        HttpClient httpClient = this.CreateMockHttpClientWithCapture(new BaseEvent[]
        {
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        }, capturedRunIds);

        AGUIAgent agent = new("agent1", "Test agent", [], httpClient, "http://localhost/agent");
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        await foreach (var _ in agent.RunStreamingAsync(messages))
        {
        }
        await foreach (var _ in agent.RunStreamingAsync(messages))
        {
        }

        // Assert
        Assert.Equal(2, capturedRunIds.Count);
        Assert.NotEqual(capturedRunIds[0], capturedRunIds[1]);
    }

    [Fact]
    public async Task RunStreamingAsync_NotifiesThreadOfNewMessages_AfterCompletionAsync()
    {
        // Arrange
        HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        AGUIAgent agent = new("agent1", "Test agent", [], httpClient, "http://localhost/agent");
        AGUIAgentThread thread = new();
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        await foreach (var _ in agent.RunStreamingAsync(messages, thread))
        {
        }

        // Assert
        Assert.NotEmpty(thread.MessageStore);
    }

    [Fact]
    public void DeserializeThread_WithValidState_DeserializesSuccessfully()
    {
        // Arrange
        AGUIAgent agent = new("agent1", "Test agent", [], new HttpClient(), "http://localhost/agent");
        AGUIAgentThread originalThread = new() { ThreadId = "thread1" };
        JsonElement serialized = originalThread.Serialize();

        // Act
        AgentThread deserialized = agent.DeserializeThread(serialized);

        // Assert
        Assert.NotNull(deserialized);
        Assert.IsType<AGUIAgentThread>(deserialized);
    }

    [Fact]
    public void DeserializeThread_PreservesThreadId_FromSerializedState()
    {
        // Arrange
        AGUIAgent agent = new("agent1", "Test agent", [], new HttpClient(), "http://localhost/agent");
        AGUIAgentThread originalThread = new() { ThreadId = "thread123" };
        JsonElement serialized = originalThread.Serialize();

        // Act
        AGUIAgentThread deserialized = (AGUIAgentThread)agent.DeserializeThread(serialized);

        // Assert
        Assert.Equal("thread123", deserialized.ThreadId);
    }

    [Fact]
    public void DeserializeThread_WithMissingThreadId_ThrowsInvalidOperationException()
    {
        // Arrange
        AGUIAgent agent = new("agent1", "Test agent", [], new HttpClient(), "http://localhost/agent");
        const string Json = "{\"WrappedState\":{}}";
        JsonElement serialized = JsonSerializer.Deserialize<JsonElement>(Json);

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => agent.DeserializeThread(serialized));
    }

    private HttpClient CreateMockHttpClient(BaseEvent[] events)
    {
        string sseContent = string.Join("", events.Select(e =>
            $"data: {JsonSerializer.Serialize(e, AGUIJsonSerializerContext.Default.BaseEvent)}\n\n"));

        Mock<HttpMessageHandler> handlerMock = new(MockBehavior.Strict);
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

        Mock<HttpMessageHandler> handlerMock = new(MockBehavior.Strict);
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
}
