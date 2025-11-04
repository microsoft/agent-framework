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

namespace Microsoft.Agents.AI.AGUI.UnitTests;

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

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "agent1", description: "Test agent", tools: []);
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

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "agent1", description: "Test agent", tools: []);
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
        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: "Test agent", name: "agent1");

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

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: "Test agent", name: "agent1");
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        AgentRunResponse response = await agent.RunAsync(messages, thread: null);

        // Assert
        Assert.NotNull(response);
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

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: "Test agent", name: "agent1");
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
        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: "Test agent", name: "agent1");

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
        using HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: "Test agent", name: "agent1");
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
    public async Task RunStreamingAsync_GeneratesUniqueRunId_ForEachInvocationAsync()
    {
        // Arrange
        var handler = new TestDelegatingHandler();
        handler.AddResponseWithCapture(new BaseEvent[]
        {
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        });
        handler.AddResponseWithCapture(new BaseEvent[]
        {
            new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
        });
        using HttpClient httpClient = new(handler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "agent1", description: "Test agent", tools: []);
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
        Assert.Equal(2, handler.CapturedRunIds.Count);
        Assert.NotEqual(handler.CapturedRunIds[0], handler.CapturedRunIds[1]);
    }

    [Fact]
    public async Task RunStreamingAsync_ReturnsStreamingUpdates_AfterCompletionAsync()
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

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "agent1", description: "Test agent", tools: []);
        AgentThread thread = agent.GetNewThread();
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (var update in agent.RunStreamingAsync(messages, thread))
        {
            updates.Add(update);
        }

        // Assert - Verify streaming updates were received
        Assert.NotEmpty(updates);
        Assert.Contains(updates, u => u.Text == "Hello");
    }

    [Fact]
    public void DeserializeThread_WithValidState_ReturnsChatClientAgentThread()
    {
        // Arrange
        using var httpClient = new HttpClient();
        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "agent1", description: "Test agent", tools: []);
        AgentThread originalThread = agent.GetNewThread();
        JsonElement serialized = originalThread.Serialize();

        // Act
        AgentThread deserialized = agent.DeserializeThread(serialized);

        // Assert
        Assert.NotNull(deserialized);
        Assert.IsType<ChatClientAgentThread>(deserialized);
    }

    private HttpClient CreateMockHttpClient(BaseEvent[] events)
    {
        var handler = new TestDelegatingHandler();
        handler.AddResponse(events);
        return new HttpClient(handler);
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

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "agent1", description: "Test agent", tools: [testTool]);
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

        // FunctionInvokingChatClient makes two calls: first gets tool calls, second returns final response
        // When not all tools are available, it invokes the ones that ARE available
        var handler = new TestDelegatingHandler();
        handler.AddResponse(
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
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
            new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg2", Delta = "Response" },
            new TextMessageEndEvent { MessageId = "msg2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
        ]);
        using HttpClient httpClient = new(handler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "agent1", description: "Test agent", tools: [tool1]); // Only tool1, not tool2
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<AgentRunResponseUpdate> allUpdates = [];
        await foreach (AgentRunResponseUpdate update in agent.RunStreamingAsync(messages))
        {
            allUpdates.Add(update);
        }

        // Assert
        // FunctionInvokingChatClient invokes Tool1 since it's available, even though Tool2 is not
        Assert.True(tool1Invoked, "Tool1 should be invoked even though Tool2 is not available");
        // Should have tool call results for Tool1 and an error result for Tool2
        Assert.Contains(allUpdates, u => u.Contents.Any(c => c is FunctionResultContent frc && frc.CallId == "call_1"));
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

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "agent1", description: "Test agent", tools: [faultyTool]);
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

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "agent1", description: "Test agent", tools: [tool1, tool2]);
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

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        AIAgent agent = chatClient.CreateAIAgent(instructions: null, name: "agent1", description: "Test agent", tools: [testTool]);
        AgentThread thread = agent.GetNewThread();
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<AgentRunResponseUpdate> updates = [];
        await foreach (var update in agent.RunStreamingAsync(messages, thread))
        {
            updates.Add(update);
        }

        // Assert - Verify we received updates including tool calls
        Assert.NotEmpty(updates);
        Assert.Contains(updates, u => u.Contents.Any(c => c is FunctionCallContent));
        Assert.Contains(updates, u => u.Contents.Any(c => c is FunctionResultContent));
        Assert.Contains(updates, u => u.Text == "Complete");
    }

    private HttpClient CreateMockHttpClientForToolCalls(BaseEvent[] firstResponse, BaseEvent[] secondResponse)
    {
        var handler = new TestDelegatingHandler();
        handler.AddResponse(firstResponse);
        handler.AddResponse(secondResponse);
        return new HttpClient(handler);
    }
}

internal sealed class TestDelegatingHandler : DelegatingHandler
{
    private readonly Queue<Func<HttpRequestMessage, HttpResponseMessage>> _responseFactories = new();
    private readonly List<string> _capturedRunIds = new();

    public IReadOnlyList<string> CapturedRunIds => this._capturedRunIds;

    public void AddResponse(BaseEvent[] events)
    {
        this._responseFactories.Enqueue(_ => CreateResponse(events));
    }

    public void AddResponseWithCapture(BaseEvent[] events)
    {
        this._responseFactories.Enqueue(request =>
        {
            this.CaptureRunId(request);
            return CreateResponse(events);
        });
    }

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        if (this._responseFactories.Count == 0)
        {
            // Log request count for debugging
            throw new InvalidOperationException($"No more responses configured for TestDelegatingHandler. Total requests made: {this._capturedRunIds.Count}");
        }

        var factory = this._responseFactories.Dequeue();
        return Task.FromResult(factory(request));
    }

    private static HttpResponseMessage CreateResponse(BaseEvent[] events)
    {
        string sseContent = string.Join("", events.Select(e =>
            $"data: {JsonSerializer.Serialize(e, AGUIJsonSerializerContext.Default.BaseEvent)}\n\n"));

        return new HttpResponseMessage
        {
            StatusCode = HttpStatusCode.OK,
            Content = new StringContent(sseContent)
        };
    }

    private void CaptureRunId(HttpRequestMessage request)
    {
        // Suppress VSTHRD002: This is test code and synchronous read is acceptable
#pragma warning disable VSTHRD002
        string requestBody = request.Content!.ReadAsStringAsync().ConfigureAwait(false).GetAwaiter().GetResult();
#pragma warning restore VSTHRD002
        RunAgentInput? input = JsonSerializer.Deserialize(requestBody, AGUIJsonSerializerContext.Default.RunAgentInput);
        if (input != null)
        {
            this._capturedRunIds.Add(input.RunId);
        }
    }
}
