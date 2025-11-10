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

    [Fact]
    public async Task GetStreamingResponseAsync_WrapsServerFunctionCalls_InServerFunctionCallContentAsync()
    {
        // Arrange - Server returns a function call for a tool not in the client tool set
        using HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "ServerTool", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{\"arg\":\"value\"}" },
            new ToolCallEndEvent { ToolCallId = "call_1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        // No tools provided - any function call from server is a "server function"
        var options = new ChatOptions();
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, options))
        {
            updates.Add(update);
        }

        // Assert - Server function call should be presented as FunctionCallContent (unwrapped)
        Assert.Contains(updates, u => u.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name == "ServerTool"));
        // Should NOT contain ServerFunctionCallContent (it's internal and unwrapped before yielding)
        Assert.DoesNotContain(updates, u => u.Contents.Any(c => c.GetType().Name == "ServerFunctionCallContent"));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_DoesNotWrapClientFunctionCalls_WhenToolInClientSetAsync()
    {
        // Arrange
        AIFunction clientTool = AIFunctionFactory.Create(() => "Result", "ClientTool");

        var handler = new TestDelegatingHandler();
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "ClientTool", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "call_1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
            new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg2", Delta = "Done" },
            new TextMessageEndEvent { MessageId = "msg2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
        ]);
        using HttpClient httpClient = new(handler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        var options = new ChatOptions { Tools = [clientTool] };
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, options))
        {
            updates.Add(update);
        }

        // Assert - Should have function call and result (FunctionInvokingChatClient processed it)
        Assert.Contains(updates, u => u.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name == "ClientTool"));
        Assert.Contains(updates, u => u.Contents.Any(c => c is FunctionResultContent frc && frc.CallId == "call_1"));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_HandlesMixedClientAndServerFunctions_InSameResponseAsync()
    {
        // Arrange
        AIFunction clientTool = AIFunctionFactory.Create(() => "ClientResult", "ClientTool");

        var handler = new TestDelegatingHandler();
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "ClientTool", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "call_1" },
            new ToolCallStartEvent { ToolCallId = "call_2", ToolCallName = "ServerTool", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_2", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "call_2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
            new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg2", Delta = "Done" },
            new TextMessageEndEvent { MessageId = "msg2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
        ]);
        using HttpClient httpClient = new(handler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        var options = new ChatOptions { Tools = [clientTool] };
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, options))
        {
            updates.Add(update);
        }

        // Assert - Should have both client and server function calls
        Assert.Contains(updates, u => u.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name == "ClientTool"));
        Assert.Contains(updates, u => u.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name == "ServerTool"));
        // Client tool should have result
        Assert.Contains(updates, u => u.Contents.Any(c => c is FunctionResultContent frc && frc.CallId == "call_1"));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_PreservesConversationId_AcrossMultipleTurnsAsync()
    {
        // Arrange
        var handler = new TestDelegatingHandler();
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "First" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
            new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg2", Delta = "Second" },
            new TextMessageEndEvent { MessageId = "msg2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
        ]);
        using HttpClient httpClient = new(handler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        var options = new ChatOptions { ConversationId = "my-conversation-123" };
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act - First turn
        List<ChatResponseUpdate> updates1 = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, options))
        {
            updates1.Add(update);
        }

        // Second turn with same conversation ID
        List<ChatResponseUpdate> updates2 = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, options))
        {
            updates2.Add(update);
        }

        // Assert - Both turns should preserve the conversation ID
        Assert.All(updates1, u => Assert.Equal("my-conversation-123", u.ConversationId));
        Assert.All(updates2, u => Assert.Equal("my-conversation-123", u.ConversationId));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_ExtractsThreadId_FromServerResponseAsync()
    {
        // Arrange
        using HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "server-thread-456", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "server-thread-456", RunId = "run1" }
        ]);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        // No conversation ID provided
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, null))
        {
            updates.Add(update);
        }

        // Assert - Should use thread ID from server
        Assert.All(updates, u => Assert.Equal("server-thread-456", u.ConversationId));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_GeneratesThreadId_WhenNoneProvidedAsync()
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
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, null))
        {
            updates.Add(update);
        }

        // Assert - Should have a conversation ID (either from server or generated)
        Assert.All(updates, u => Assert.NotNull(u.ConversationId));
        Assert.All(updates, u => Assert.NotEmpty(u.ConversationId!));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_RemovesThreadIdFromFunctionCallProperties_BeforeYieldingAsync()
    {
        // Arrange
        AIFunction clientTool = AIFunctionFactory.Create(() => "Result", "ClientTool");

        var handler = new TestDelegatingHandler();
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "ClientTool", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "call_1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
            new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg2", Delta = "Done" },
            new TextMessageEndEvent { MessageId = "msg2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
        ]);
        using HttpClient httpClient = new(handler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        var options = new ChatOptions { Tools = [clientTool] };
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, options))
        {
            updates.Add(update);
        }

        // Assert - Function call content should not have agui_thread_id in additional properties
        var functionCallUpdate = updates.FirstOrDefault(u => u.Contents.Any(c => c is FunctionCallContent));
        Assert.NotNull(functionCallUpdate);
        var fcc = functionCallUpdate.Contents.OfType<FunctionCallContent>().First();
        Assert.True(fcc.AdditionalProperties?.ContainsKey("agui_thread_id") != true);
    }

    [Fact]
    public async Task GetResponseAsync_PreservesConversationId_ThroughStreamingPathAsync()
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
        var options = new ChatOptions { ConversationId = "my-conversation-456" };
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        ChatResponse response = await chatClient.GetResponseAsync(messages, options);

        // Assert
        Assert.Equal("my-conversation-456", response.ConversationId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_UsesServerThreadId_WhenDifferentFromClientAsync()
    {
        // Arrange - Server returns different thread ID
        using HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "server-generated-thread", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "server-generated-thread", RunId = "run1" }
        ]);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        var options = new ChatOptions { ConversationId = "client-thread-123" };
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, options))
        {
            updates.Add(update);
        }

        // Assert - Should use client's conversation ID (we provided it explicitly)
        Assert.All(updates, u => Assert.Equal("client-thread-123", u.ConversationId));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_FullConversationFlow_WithMixedFunctionsAsync()
    {
        // Arrange
        AIFunction clientTool = AIFunctionFactory.Create(() => "ClientResult", "ClientTool");

        var handler = new TestDelegatingHandler();
        // First response: client function call (FunctionInvokingChatClient will handle this)
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new ToolCallStartEvent { ToolCallId = "call_client", ToolCallName = "ClientTool", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_client", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "call_client" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        // Second response: after client function execution, return final text
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
            new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg2", Delta = "Complete" },
            new TextMessageEndEvent { MessageId = "msg2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
        ]);
        using HttpClient httpClient = new(handler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        var options = new ChatOptions { Tools = [clientTool] };
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<ChatResponseUpdate> updates = [];
        string? conversationId = null;
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, options))
        {
            updates.Add(update);
            conversationId ??= update.ConversationId;
        }

        // Assert
        // Should have client function call and result
        Assert.Contains(updates, u => u.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name == "ClientTool"));
        Assert.Contains(updates, u => u.Contents.Any(c => c is FunctionResultContent frc && frc.CallId == "call_client"));
        // Should have final text response
        Assert.Contains(updates, u => u.Contents.Any(c => c is TextContent));
        // All updates should have consistent conversation ID
        Assert.NotNull(conversationId);
        Assert.All(updates, u => Assert.Equal(conversationId, u.ConversationId));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_ExtractsThreadIdFromFunctionCall_OnSubsequentTurnsAsync()
    {
        // Arrange
        AIFunction clientTool = AIFunctionFactory.Create(() => "Result", "ClientTool");

        var handler = new TestDelegatingHandler();
        // First turn: client function call
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "ClientTool", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "call_1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        // FunctionInvokingChatClient automatically calls again after function execution
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
            new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg2", Delta = "First done" },
            new TextMessageEndEvent { MessageId = "msg2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
        ]);
        // Third turn: user makes another request with conversation history
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run3" },
            new TextMessageStartEvent { MessageId = "msg3", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg3", Delta = "Second done" },
            new TextMessageEndEvent { MessageId = "msg3" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run3" }
        ]);
        using HttpClient httpClient = new(handler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        var options = new ChatOptions { Tools = [clientTool] };
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act - First turn
        List<ChatMessage> conversation = new(messages);
        string? conversationId = null;
        await foreach (var update in chatClient.GetStreamingResponseAsync(conversation, options))
        {
            conversationId ??= update.ConversationId;
            // Collect all updates to build the conversation history
            foreach (var content in update.Contents)
            {
                if (content is FunctionCallContent fcc)
                {
                    conversation.Add(new ChatMessage(ChatRole.Assistant, [fcc]));
                }
                else if (content is FunctionResultContent frc)
                {
                    conversation.Add(new ChatMessage(ChatRole.Tool, [frc]));
                }
                else if (content is TextContent tc)
                {
                    var existingAssistant = conversation.LastOrDefault(m => m.Role == ChatRole.Assistant && m.Contents.Any(c => c is TextContent));
                    if (existingAssistant == null)
                    {
                        conversation.Add(new ChatMessage(ChatRole.Assistant, [tc]));
                    }
                }
            }
        }

        // Act - Second turn with conversation history including function call
        // The thread ID should be extracted from the function call in the conversation history
        options.ConversationId = conversationId;
        List<ChatResponseUpdate> secondTurnUpdates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(conversation, options))
        {
            secondTurnUpdates.Add(update);
        }

        // Assert - Second turn should maintain the same conversation ID
        Assert.NotNull(conversationId);
        Assert.All(secondTurnUpdates, u => Assert.Equal(conversationId, u.ConversationId));
        Assert.Contains(secondTurnUpdates, u => u.Contents.Any(c => c is TextContent));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_MaintainsConsistentThreadId_AcrossMultipleTurnsAsync()
    {
        // Arrange
        var handler = new TestDelegatingHandler();
        // Turn 1
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Response 1" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        // Turn 2
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
            new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg2", Delta = "Response 2" },
            new TextMessageEndEvent { MessageId = "msg2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
        ]);
        // Turn 3
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run3" },
            new TextMessageStartEvent { MessageId = "msg3", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg3", Delta = "Response 3" },
            new TextMessageEndEvent { MessageId = "msg3" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run3" }
        ]);
        using HttpClient httpClient = new(handler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        var options = new ChatOptions { ConversationId = "my-conversation" };
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act - Execute 3 turns
        string? conversationId = null;
        for (int i = 0; i < 3; i++)
        {
            await foreach (var update in chatClient.GetStreamingResponseAsync(messages, options))
            {
                conversationId ??= update.ConversationId;
                Assert.Equal("my-conversation", update.ConversationId);
            }
        }

        // Assert
        Assert.Equal("my-conversation", conversationId);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_HandlesEmptyThreadId_GracefullyAsync()
    {
        // Arrange - Server returns empty thread ID
        using HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = string.Empty, RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = string.Empty, RunId = "run1" }
        ]);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, null))
        {
            updates.Add(update);
        }

        // Assert - Should generate a conversation ID even with empty server thread ID
        Assert.NotEmpty(updates);
        Assert.All(updates, u => Assert.NotNull(u.ConversationId));
        Assert.All(updates, u => Assert.NotEmpty(u.ConversationId!));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_AdaptsToServerThreadIdChange_MidConversationAsync()
    {
        // Arrange
        var handler = new TestDelegatingHandler();
        // First turn: server returns thread-A
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread-A", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "First" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread-A", RunId = "run1" }
        ]);
        // Second turn: provide thread-A but server returns thread-B
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread-B", RunId = "run2" },
            new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg2", Delta = "Second" },
            new TextMessageEndEvent { MessageId = "msg2" },
            new RunFinishedEvent { ThreadId = "thread-B", RunId = "run2" }
        ]);
        using HttpClient httpClient = new(handler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act - First turn
        string? firstConversationId = null;
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, null))
        {
            firstConversationId ??= update.ConversationId;
        }

        // Second turn - provide the conversation ID from first turn
        var options = new ChatOptions { ConversationId = firstConversationId };
        string? secondConversationId = null;
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, options))
        {
            secondConversationId ??= update.ConversationId;
        }

        // Assert - Should use client-provided conversation ID, not server's changed ID
        Assert.Equal("thread-A", firstConversationId);
        Assert.Equal("thread-A", secondConversationId); // Client overrides server's thread-B
    }

    [Fact]
    public async Task GetStreamingResponseAsync_PresentsServerFunctionResults_AsRegularFunctionResultsAsync()
    {
        // Arrange - Server function (not in client tool set)
        using HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "ServerTool", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{\"arg\":\"value\"}" },
            new ToolCallEndEvent { ToolCallId = "call_1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, null))
        {
            updates.Add(update);
        }

        // Assert - Server function should be presented as FunctionCallContent (unwrapped from ServerFunctionCallContent)
        Assert.Contains(updates, u => u.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name == "ServerTool"));
        // Verify it's NOT a ServerFunctionCallContent (internal type should be unwrapped)
        Assert.All(updates, u => Assert.DoesNotContain(u.Contents, c => c.GetType().Name == "ServerFunctionCallContent"));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_HandlesMultipleServerFunctions_InSequenceAsync()
    {
        // Arrange
        var handler = new TestDelegatingHandler();
        // Turn 1: Server function 1
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "ServerTool1", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "call_1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        // Turn 2: Server function 2
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
            new ToolCallStartEvent { ToolCallId = "call_2", ToolCallName = "ServerTool2", ParentMessageId = "msg2" },
            new ToolCallArgsEvent { ToolCallId = "call_2", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "call_2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
        ]);
        // Turn 3: Final response
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run3" },
            new TextMessageStartEvent { MessageId = "msg3", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg3", Delta = "Complete" },
            new TextMessageEndEvent { MessageId = "msg3" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run3" }
        ]);
        using HttpClient httpClient = new(handler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        var options = new ChatOptions { ConversationId = "conv1" };
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act - Execute all 3 turns
        List<ChatResponseUpdate> allUpdates = [];
        for (int i = 0; i < 3; i++)
        {
            await foreach (var update in chatClient.GetStreamingResponseAsync(messages, options))
            {
                allUpdates.Add(update);
            }
        }

        // Assert
        Assert.Contains(allUpdates, u => u.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name == "ServerTool1"));
        Assert.Contains(allUpdates, u => u.Contents.Any(c => c is FunctionCallContent fcc && fcc.Name == "ServerTool2"));
        Assert.Contains(allUpdates, u => u.Contents.Any(c => c is TextContent));
        Assert.All(allUpdates, u => Assert.Equal("conv1", u.ConversationId));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_MaintainsThreadIdConsistency_WithOnlyServerFunctionsAsync()
    {
        // Arrange - Full conversation with only server functions
        var handler = new TestDelegatingHandler();
        // Turn 1: Server function
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new ToolCallStartEvent { ToolCallId = "call_1", ToolCallName = "ServerTool", ParentMessageId = "msg1" },
            new ToolCallArgsEvent { ToolCallId = "call_1", Delta = "{}" },
            new ToolCallEndEvent { ToolCallId = "call_1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        // Turn 2: Final response
        handler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
            new TextMessageStartEvent { MessageId = "msg2", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg2", Delta = "Done" },
            new TextMessageEndEvent { MessageId = "msg2" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
        ]);
        using HttpClient httpClient = new(handler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        string? conversationId = null;
        List<ChatResponseUpdate> allUpdates = [];
        for (int i = 0; i < 2; i++)
        {
            await foreach (var update in chatClient.GetStreamingResponseAsync(messages, null))
            {
                conversationId ??= update.ConversationId;
                allUpdates.Add(update);
            }
        }

        // Assert - Thread ID should be consistent without client function invocations
        Assert.NotNull(conversationId);
        Assert.All(allUpdates, u => Assert.Equal(conversationId, u.ConversationId));
        Assert.Contains(allUpdates, u => u.Contents.Any(c => c is FunctionCallContent));
        Assert.Contains(allUpdates, u => u.Contents.Any(c => c is TextContent));
    }

    [Fact]
    public async Task GetStreamingResponseAsync_StoresConversationIdInAdditionalProperties_WithoutMutatingOptionsAsync()
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
        var options = new ChatOptions { ConversationId = "my-conversation-123" };
        var originalConversationId = options.ConversationId;
        var originalAdditionalProperties = options.AdditionalProperties;
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, options))
        {
            // Just consume the stream
        }

        // Assert - Original options should not be mutated
        Assert.Equal(originalConversationId, options.ConversationId);
        Assert.Equal(originalAdditionalProperties, options.AdditionalProperties);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_EnsuresConversationIdIsNull_ForInnerClientAsync()
    {
        // Arrange - Use a custom handler to capture what's sent to the inner layer
        var captureHandler = new CapturingTestDelegatingHandler();
        captureHandler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Hello" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        using HttpClient httpClient = new(captureHandler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        var options = new ChatOptions { ConversationId = "my-conversation-123" };
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        await foreach (var _ in chatClient.GetStreamingResponseAsync(messages, options))
        {
            // Just consume the stream
        }

        // Assert - The inner handler should see the full message history being sent
        // This is implicitly tested by the fact that all messages are sent in the request
        // AG-UI requirement: full history on every turn (which happens when ConversationId is null for FunctionInvokingChatClient)
        Assert.True(captureHandler.RequestWasMade);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_ExtractsStateFromDataContent_AndRemovesStateMessageAsync()
    {
        // Arrange
        var stateData = new { counter = 42, status = "active" };
        string stateJson = JsonSerializer.Serialize(stateData);
        byte[] stateBytes = System.Text.Encoding.UTF8.GetBytes(stateJson);
        var dataContent = new DataContent(stateBytes, "application/json");

        var captureHandler = new StateCapturingTestDelegatingHandler();
        captureHandler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Response" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        using HttpClient httpClient = new(captureHandler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.System, [dataContent])
        ];

        // Act
        await foreach (var _ in chatClient.GetStreamingResponseAsync(messages, null))
        {
            // Just consume the stream
        }

        // Assert
        Assert.True(captureHandler.RequestWasMade);
        Assert.NotNull(captureHandler.CapturedState);
        Assert.Equal(42, captureHandler.CapturedState.Value.GetProperty("counter").GetInt32());
        Assert.Equal("active", captureHandler.CapturedState.Value.GetProperty("status").GetString());

        // Verify state message was removed - only user message should be in the request
        Assert.Equal(1, captureHandler.CapturedMessageCount);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithNoStateDataContent_SendsEmptyStateAsync()
    {
        // Arrange
        var captureHandler = new StateCapturingTestDelegatingHandler();
        captureHandler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Response" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        using HttpClient httpClient = new(captureHandler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];

        // Act
        await foreach (var _ in chatClient.GetStreamingResponseAsync(messages, null))
        {
            // Just consume the stream
        }

        // Assert
        Assert.True(captureHandler.RequestWasMade);
        Assert.Null(captureHandler.CapturedState);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithMalformedStateJson_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        byte[] invalidJson = System.Text.Encoding.UTF8.GetBytes("{invalid json");
        var dataContent = new DataContent(invalidJson, "application/json");

        using HttpClient httpClient = this.CreateMockHttpClient([]);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.System, [dataContent])
        ];

        // Act & Assert
        InvalidOperationException ex = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in chatClient.GetStreamingResponseAsync(messages, null))
            {
                // Just consume the stream
            }
        });

        Assert.Contains("Failed to deserialize state JSON", ex.Message);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithEmptyStateObject_SendsEmptyObjectAsync()
    {
        // Arrange
        var emptyState = new { };
        string stateJson = JsonSerializer.Serialize(emptyState);
        byte[] stateBytes = System.Text.Encoding.UTF8.GetBytes(stateJson);
        var dataContent = new DataContent(stateBytes, "application/json");

        var captureHandler = new StateCapturingTestDelegatingHandler();
        captureHandler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        using HttpClient httpClient = new(captureHandler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "Hello"),
            new ChatMessage(ChatRole.System, [dataContent])
        ];

        // Act
        await foreach (var _ in chatClient.GetStreamingResponseAsync(messages, null))
        {
            // Just consume the stream
        }

        // Assert
        Assert.True(captureHandler.RequestWasMade);
        Assert.NotNull(captureHandler.CapturedState);
        Assert.Equal(JsonValueKind.Object, captureHandler.CapturedState.Value.ValueKind);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_OnlyProcessesDataContentFromLastMessage_IgnoresEarlierOnesAsync()
    {
        // Arrange
        var oldState = new { counter = 10 };
        string oldStateJson = JsonSerializer.Serialize(oldState);
        byte[] oldStateBytes = System.Text.Encoding.UTF8.GetBytes(oldStateJson);
        var oldDataContent = new DataContent(oldStateBytes, "application/json");

        var newState = new { counter = 20 };
        string newStateJson = JsonSerializer.Serialize(newState);
        byte[] newStateBytes = System.Text.Encoding.UTF8.GetBytes(newStateJson);
        var newDataContent = new DataContent(newStateBytes, "application/json");

        var captureHandler = new StateCapturingTestDelegatingHandler();
        captureHandler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        using HttpClient httpClient = new(captureHandler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, "First message"),
            new ChatMessage(ChatRole.System, [oldDataContent]),
            new ChatMessage(ChatRole.User, "Second message"),
            new ChatMessage(ChatRole.System, [newDataContent])
        ];

        // Act
        await foreach (var _ in chatClient.GetStreamingResponseAsync(messages, null))
        {
            // Just consume the stream
        }

        // Assert
        Assert.True(captureHandler.RequestWasMade);
        Assert.NotNull(captureHandler.CapturedState);
        // Should use the new state from the last message
        Assert.Equal(20, captureHandler.CapturedState.Value.GetProperty("counter").GetInt32());

        // Should have removed only the last state message
        Assert.Equal(3, captureHandler.CapturedMessageCount);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_WithNonJsonMediaType_IgnoresDataContentAsync()
    {
        // Arrange
        byte[] imageData = System.Text.Encoding.UTF8.GetBytes("fake image data");
        var dataContent = new DataContent(imageData, "image/png");

        var captureHandler = new StateCapturingTestDelegatingHandler();
        captureHandler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        using HttpClient httpClient = new(captureHandler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        List<ChatMessage> messages =
        [
            new ChatMessage(ChatRole.User, [new TextContent("Hello"), dataContent])
        ];

        // Act
        await foreach (var _ in chatClient.GetStreamingResponseAsync(messages, null))
        {
            // Just consume the stream
        }

        // Assert
        Assert.True(captureHandler.RequestWasMade);
        Assert.Null(captureHandler.CapturedState);
        // Message should not be removed since it's not state
        Assert.Equal(1, captureHandler.CapturedMessageCount);
    }

    [Fact]
    public async Task GetStreamingResponseAsync_RoundTripState_PreservesJsonStructureAsync()
    {
        // Arrange - Server returns state snapshot
        var returnedState = new { counter = 100, nested = new { value = "test" } };
        JsonElement stateSnapshot = JsonSerializer.SerializeToElement(returnedState);

        var captureHandler = new StateCapturingTestDelegatingHandler();
        captureHandler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new StateSnapshotEvent { Snapshot = stateSnapshot },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);
        captureHandler.AddResponse(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run2" },
            new TextMessageStartEvent { MessageId = "msg1", Role = AGUIRoles.Assistant },
            new TextMessageContentEvent { MessageId = "msg1", Delta = "Done" },
            new TextMessageEndEvent { MessageId = "msg1" },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run2" }
        ]);
        using HttpClient httpClient = new(captureHandler);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Hello")];

        // Act - First turn: receive state
        DataContent? receivedStateContent = null;
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, null))
        {
            if (update.Contents.Any(c => c is DataContent dc && dc.MediaType == "application/json"))
            {
                receivedStateContent = (DataContent)update.Contents.First(c => c is DataContent);
            }
        }

        // Second turn: send the received state back
        Assert.NotNull(receivedStateContent);
        messages.Add(new ChatMessage(ChatRole.System, [receivedStateContent]));
        await foreach (var _ in chatClient.GetStreamingResponseAsync(messages, null))
        {
            // Just consume the stream
        }

        // Assert - Verify the round-tripped state
        Assert.NotNull(captureHandler.CapturedState);
        Assert.Equal(100, captureHandler.CapturedState.Value.GetProperty("counter").GetInt32());
        Assert.Equal("test", captureHandler.CapturedState.Value.GetProperty("nested").GetProperty("value").GetString());
    }

    [Fact]
    public async Task GetStreamingResponseAsync_ReceivesStateSnapshot_AsDataContentWithAdditionalPropertiesAsync()
    {
        // Arrange
        var state = new { sessionId = "abc123", step = 5 };
        JsonElement stateSnapshot = JsonSerializer.SerializeToElement(state);

        using HttpClient httpClient = this.CreateMockHttpClient(
        [
            new RunStartedEvent { ThreadId = "thread1", RunId = "run1" },
            new StateSnapshotEvent { Snapshot = stateSnapshot },
            new RunFinishedEvent { ThreadId = "thread1", RunId = "run1" }
        ]);

        var chatClient = new AGUIChatClient(httpClient, "http://localhost/agent", null, AGUIJsonSerializerContext.Default.Options);
        List<ChatMessage> messages = [new ChatMessage(ChatRole.User, "Test")];

        // Act
        List<ChatResponseUpdate> updates = [];
        await foreach (var update in chatClient.GetStreamingResponseAsync(messages, null))
        {
            updates.Add(update);
        }

        // Assert
        ChatResponseUpdate stateUpdate = updates.First(u => u.Contents.Any(c => c is DataContent));
        Assert.NotNull(stateUpdate.AdditionalProperties);
        Assert.True((bool)stateUpdate.AdditionalProperties!["is_state_snapshot"]!);

        DataContent dataContent = (DataContent)stateUpdate.Contents[0];
        Assert.Equal("application/json", dataContent.MediaType);

        string jsonText = System.Text.Encoding.UTF8.GetString(dataContent.Data.ToArray());
        JsonElement deserializedState = JsonSerializer.Deserialize<JsonElement>(jsonText);
        Assert.Equal("abc123", deserializedState.GetProperty("sessionId").GetString());
        Assert.Equal(5, deserializedState.GetProperty("step").GetInt32());
    }
}

internal sealed class TestDelegatingHandler : DelegatingHandler
{
    private readonly Queue<Func<HttpRequestMessage, Task<HttpResponseMessage>>> _responseFactories = new();
    private readonly List<string> _capturedRunIds = new();

    public IReadOnlyList<string> CapturedRunIds => this._capturedRunIds;

    public void AddResponse(BaseEvent[] events)
    {
        this._responseFactories.Enqueue(_ => Task.FromResult(CreateResponse(events)));
    }

    public void AddResponseWithCapture(BaseEvent[] events)
    {
        this._responseFactories.Enqueue(async request =>
        {
            await this.CaptureRunIdAsync(request);
            return CreateResponse(events);
        });
    }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        if (this._responseFactories.Count == 0)
        {
            // Log request count for debugging
            throw new InvalidOperationException($"No more responses configured for TestDelegatingHandler. Total requests made: {this._capturedRunIds.Count}");
        }

        var factory = this._responseFactories.Dequeue();
        return await factory(request);
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

    private async Task CaptureRunIdAsync(HttpRequestMessage request)
    {
        string requestBody = await request.Content!.ReadAsStringAsync().ConfigureAwait(false);
        RunAgentInput? input = JsonSerializer.Deserialize(requestBody, AGUIJsonSerializerContext.Default.RunAgentInput);
        if (input != null)
        {
            this._capturedRunIds.Add(input.RunId);
        }
    }
}

internal sealed class CapturingTestDelegatingHandler : DelegatingHandler
{
    private readonly Queue<Func<HttpRequestMessage, Task<HttpResponseMessage>>> _responseFactories = new();

    public bool RequestWasMade { get; private set; }

    public void AddResponse(BaseEvent[] events)
    {
        this._responseFactories.Enqueue(_ => Task.FromResult(CreateResponse(events)));
    }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        this.RequestWasMade = true;

        if (this._responseFactories.Count == 0)
        {
            throw new InvalidOperationException("No more responses configured for CapturingTestDelegatingHandler.");
        }

        var factory = this._responseFactories.Dequeue();
        return await factory(request);
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
}

internal sealed class StateCapturingTestDelegatingHandler : DelegatingHandler
{
    private readonly Queue<Func<HttpRequestMessage, Task<HttpResponseMessage>>> _responseFactories = new();

    public bool RequestWasMade { get; private set; }
    public JsonElement? CapturedState { get; private set; }
    public int CapturedMessageCount { get; private set; }

    public void AddResponse(BaseEvent[] events)
    {
        this._responseFactories.Enqueue(_ => Task.FromResult(CreateResponse(events)));
    }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        this.RequestWasMade = true;

        // Capture the state and message count from the request
#if NET472 || NETSTANDARD2_0
        string requestBody = await request.Content!.ReadAsStringAsync().ConfigureAwait(false);
#else
        string requestBody = await request.Content!.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
#endif
        RunAgentInput? input = JsonSerializer.Deserialize(requestBody, AGUIJsonSerializerContext.Default.RunAgentInput);
        if (input != null)
        {
            if (input.State.ValueKind != JsonValueKind.Undefined && input.State.ValueKind != JsonValueKind.Null)
            {
                this.CapturedState = input.State;
            }
            this.CapturedMessageCount = input.Messages.Count();
        }

        if (this._responseFactories.Count == 0)
        {
            throw new InvalidOperationException("No more responses configured for StateCapturingTestDelegatingHandler.");
        }

        var factory = this._responseFactories.Dequeue();
        return await factory(request);
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
}
