// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AAgent"/> class.
/// </summary>
public sealed class A2AAgentTests : IDisposable
{
    private readonly HttpClient _httpClient;
    private readonly A2AClientHttpMessageHandlerStub _handler;
    private readonly A2AClient _a2aClient;
    private readonly A2AAgent _agent;

    public A2AAgentTests()
    {
        this._handler = new A2AClientHttpMessageHandlerStub();
        this._httpClient = new HttpClient(this._handler, false);
        this._a2aClient = new A2AClient(new Uri("http://test-endpoint"), this._httpClient);
        this._agent = new A2AAgent(this._a2aClient);
    }

    [Fact]
    public void Constructor_WithAllParameters_InitializesPropertiesCorrectly()
    {
        // Arrange
        const string TestId = "test-id";
        const string TestName = "test-name";
        const string TestDescription = "test-description";

        // Act
        var agent = new A2AAgent(this._a2aClient, TestId, TestName, TestDescription);

        // Assert
        Assert.Equal(TestId, agent.Id);
        Assert.Equal(TestName, agent.Name);
        Assert.Equal(TestDescription, agent.Description);
    }

    [Fact]
    public void Constructor_WithNullA2AClient_ThrowsArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new A2AAgent(null!));

    [Fact]
    public void Constructor_WithIA2AClient_InitializesCorrectly()
    {
        // Arrange
        IA2AClient ia2aClient = this._a2aClient;

        // Act
        var agent = new A2AAgent(ia2aClient, "ia2a-id", "IA2A Agent", "An agent from IA2AClient");

        // Assert
        Assert.Equal("ia2a-id", agent.Id);
        Assert.Equal("IA2A Agent", agent.Name);
        Assert.Equal("An agent from IA2AClient", agent.Description);
    }

    [Fact]
    public void Constructor_WithDefaultParameters_UsesBaseProperties()
    {
        // Act
        var agent = new A2AAgent(this._a2aClient);

        // Assert
        Assert.NotNull(agent.Id);
        Assert.NotEmpty(agent.Id);
        Assert.Null(agent.Name);
        Assert.Null(agent.Description);
    }

    [Fact]
    public async Task RunAsync_AllowsNonUserRoleMessagesAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.System, "I am a system message"),
            new(ChatRole.Assistant, "I am an assistant message"),
            new(ChatRole.User, "Valid user message")
        };

        // Act & Assert
        await this._agent.RunAsync(inputMessages);
    }

    [Fact]
    public async Task RunAsync_WithValidUserMessage_RunsSuccessfullyAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new SendMessageResponse
        {
            Message = new Message
            {
                MessageId = "response-123",
                Role = Role.Agent,
                Parts =
                [
                    new Part { Text = "Hello! How can I help you today?" }
                ]
            }
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello, world!")
        };

        // Act
        var result = await this._agent.RunAsync(inputMessages);

        // Assert input message sent to A2AClient
        var inputMessage = this._handler.CapturedSendMessageRequest?.Message;
        Assert.NotNull(inputMessage);
        Assert.Single(inputMessage.Parts);
        Assert.Equal(Role.User, inputMessage.Role);
        Assert.Equal("Hello, world!", inputMessage.Parts[0].Text);

        // Assert response from A2AClient is converted correctly
        Assert.NotNull(result);
        Assert.Equal(this._agent.Id, result.AgentId);
        Assert.Equal("response-123", result.ResponseId);

        Assert.NotNull(result.RawRepresentation);
        Assert.IsType<Message>(result.RawRepresentation);
        Assert.Equal("response-123", ((Message)result.RawRepresentation).MessageId);

        Assert.Single(result.Messages);
        Assert.Equal(ChatRole.Assistant, result.Messages[0].Role);
        Assert.Equal("Hello! How can I help you today?", result.Messages[0].Text);
        Assert.Equal(ChatFinishReason.Stop, result.FinishReason);
    }

    [Fact]
    public async Task RunAsync_WithNewSession_UpdatesSessionConversationIdAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new SendMessageResponse
        {
            Message = new Message
            {
                MessageId = "response-123",
                Role = Role.Agent,
                Parts =
                [
                    new Part { Text = "Response" }
                ],
                ContextId = "new-context-id"
            }
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var session = await this._agent.CreateSessionAsync();

        // Act
        await this._agent.RunAsync(inputMessages, session);

        // Assert
        Assert.IsType<A2AAgentSession>(session);
        var a2aSession = (A2AAgentSession)session;
        Assert.Equal("new-context-id", a2aSession.ContextId);
    }

    [Fact]
    public async Task RunAsync_WithExistingSession_SetConversationIdToMessageAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var session = await this._agent.CreateSessionAsync();
        var a2aSession = (A2AAgentSession)session;
        a2aSession.ContextId = "existing-context-id";

        // Act
        await this._agent.RunAsync(inputMessages, session);

        // Assert
        var message = this._handler.CapturedSendMessageRequest?.Message;
        Assert.NotNull(message);
        Assert.Equal("existing-context-id", message.ContextId);
    }

    [Fact]
    public async Task RunAsync_WithSessionHavingDifferentContextId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        this._handler.ResponseToReturn = new SendMessageResponse
        {
            Message = new Message
            {
                MessageId = "response-123",
                Role = Role.Agent,
                Parts =
                [
                    new Part { Text = "Response" }
                ],
                ContextId = "different-context"
            }
        };

        var session = await this._agent.CreateSessionAsync();
        var a2aSession = (A2AAgentSession)session;
        a2aSession.ContextId = "existing-context-id";

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => this._agent.RunAsync(inputMessages, session));
    }

    [Fact]
    public async Task RunStreamingAsync_WithValidUserMessage_YieldsAgentResponseUpdatesAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello, streaming!")
        };

        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Message = new Message
            {
                MessageId = "stream-1",
                Role = Role.Agent,
                Parts = [new Part { Text = "Hello" }],
                ContextId = "stream-context"
            }
        };

        // Act
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in this._agent.RunStreamingAsync(inputMessages))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);

        // Assert input message sent to A2AClient
        var inputMessage = this._handler.CapturedSendMessageRequest?.Message;
        Assert.NotNull(inputMessage);
        Assert.Single(inputMessage.Parts);
        Assert.Equal(Role.User, inputMessage.Role);
        Assert.Equal("Hello, streaming!", inputMessage.Parts[0].Text);

        // Assert response from A2AClient is converted correctly
        Assert.Equal(ChatRole.Assistant, updates[0].Role);
        Assert.Equal("Hello", updates[0].Text);
        Assert.Equal("stream-1", updates[0].MessageId);
        Assert.Equal(this._agent.Id, updates[0].AgentId);
        Assert.Equal("stream-1", updates[0].ResponseId);
        Assert.Equal(ChatFinishReason.Stop, updates[0].FinishReason);
        Assert.IsType<Message>(updates[0].RawRepresentation);
        Assert.Equal("stream-1", ((Message)updates[0].RawRepresentation!).MessageId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithSession_UpdatesSessionConversationIdAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test streaming")
        };

        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Message = new Message
            {
                MessageId = "stream-1",
                Role = Role.Agent,
                Parts = [new Part { Text = "Response" }],
                ContextId = "new-stream-context"
            }
        };

        var session = await this._agent.CreateSessionAsync();

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync(inputMessages, session))
        {
            // Just iterate through to trigger the logic
        }

        // Assert
        var a2aSession = (A2AAgentSession)session;
        Assert.Equal("new-stream-context", a2aSession.ContextId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithExistingSession_SetConversationIdToMessageAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test streaming")
        };

        this._handler.StreamingResponseToReturn = new StreamResponse { Message = new Message() };

        var session = await this._agent.CreateSessionAsync();
        var a2aSession = (A2AAgentSession)session;
        a2aSession.ContextId = "existing-context-id";

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync(inputMessages, session))
        {
            // Just iterate through to trigger the logic
        }

        // Assert
        var message = this._handler.CapturedSendMessageRequest?.Message;
        Assert.NotNull(message);
        Assert.Equal("existing-context-id", message.ContextId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithSessionHavingDifferentContextId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var session = await this._agent.CreateSessionAsync();
        var a2aSession = (A2AAgentSession)session;
        a2aSession.ContextId = "existing-context-id";

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test streaming")
        };

        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Message = new Message
            {
                MessageId = "stream-1",
                Role = Role.Agent,
                Parts = [new Part { Text = "Response" }],
                ContextId = "different-context"
            }
        };

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var update in this._agent.RunStreamingAsync(inputMessages, session))
            {
            }
        });
    }

    [Fact]
    public async Task RunStreamingAsync_AllowsNonUserRoleMessagesAsync()
    {
        // Arrange
        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Message = new Message
            {
                MessageId = "stream-1",
                Role = Role.Agent,
                Parts = [new Part { Text = "Response" }],
                ContextId = "new-stream-context"
            }
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.System, "I am a system message"),
            new(ChatRole.Assistant, "I am an assistant message"),
            new(ChatRole.User, "Valid user message")
        };

        // Act & Assert
        await foreach (var _ in this._agent.RunStreamingAsync(inputMessages))
        {
            // Just iterate through to trigger the logic
        }
    }

    [Fact]
    public async Task RunAsync_WithHostedFileContent_ConvertsToFilePartAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User,
            [
                new TextContent("Check this file:"),
                new UriContent("https://example.com/file.pdf", "application/pdf")
            ])
        };

        // Act
        await this._agent.RunAsync(inputMessages);

        // Assert
        var message = this._handler.CapturedSendMessageRequest?.Message;
        Assert.NotNull(message);
        Assert.Equal(2, message.Parts.Count);
        Assert.Equal(PartContentCase.Text, message.Parts[0].ContentCase);
        Assert.Equal("Check this file:", message.Parts[0].Text);
        Assert.Equal(PartContentCase.Url, message.Parts[1].ContentCase);
        Assert.Equal("https://example.com/file.pdf", message.Parts[1].Url);
    }

    [Fact]
    public async Task RunAsync_WithContinuationTokenAndMessages_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var options = new AgentRunOptions { ContinuationToken = new A2AContinuationToken("task-123") };

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => this._agent.RunAsync(inputMessages, null, options));
    }

    [Fact]
    public async Task RunAsync_WithContinuationToken_CallsGetTaskAsyncAsync()
    {
        // Arrange
        this._handler.AgentTaskToReturn = new AgentTask
        {
            Id = "task-123",
            ContextId = "context-123",
            Status = new() { State = TaskState.Submitted }
        };

        var options = new AgentRunOptions { ContinuationToken = new A2AContinuationToken("task-123") };

        // Act
        await this._agent.RunAsync([], options: options);

        // Assert
        Assert.Equal("GetTask", this._handler.CapturedJsonRpcRequest?.Method);
        Assert.Equal("task-123", this._handler.CapturedGetTaskRequest?.Id);
    }

    [Fact]
    public async Task RunAsync_WithTaskInSessionAndMessage_AddTaskAsReferencesToMessageAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new SendMessageResponse
        {
            Message = new Message
            {
                MessageId = "response-123",
                Role = Role.Agent,
                Parts = [new Part { Text = "Response to task" }]
            }
        };

        var session = (A2AAgentSession)await this._agent.CreateSessionAsync();
        session.TaskId = "task-123";

        var inputMessage = new ChatMessage(ChatRole.User, "Please make the background transparent");

        // Act
        await this._agent.RunAsync(inputMessage, session);

        // Assert
        var message = this._handler.CapturedSendMessageRequest?.Message;
        Assert.Null(message?.TaskId);
        Assert.NotNull(message?.ReferenceTaskIds);
        Assert.Contains("task-123", message.ReferenceTaskIds);
    }

    [Fact]
    public async Task RunAsync_WithAgentTask_UpdatesSessionTaskIdAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new SendMessageResponse
        {
            Task = new AgentTask
            {
                Id = "task-456",
                ContextId = "context-789",
                Status = new() { State = TaskState.Submitted }
            }
        };

        var session = await this._agent.CreateSessionAsync();

        // Act
        await this._agent.RunAsync("Start a task", session);

        // Assert
        var a2aSession = (A2AAgentSession)session;
        Assert.Equal("task-456", a2aSession.TaskId);
    }

    [Fact]
    public async Task RunAsync_WithAgentTaskResponse_ReturnsTaskResponseCorrectlyAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new SendMessageResponse
        {
            Task = new AgentTask
            {
                Id = "task-789",
                ContextId = "context-456",
                Status = new() { State = TaskState.Submitted },
                Metadata = new Dictionary<string, JsonElement>
            {
                { "key1", JsonSerializer.SerializeToElement("value1") },
                { "count", JsonSerializer.SerializeToElement(42) }
            }
            }
        };

        var session = await this._agent.CreateSessionAsync();

        // Act
        var result = await this._agent.RunAsync("Start a long-running task", session);

        // Assert - verify task is converted correctly
        Assert.NotNull(result);
        Assert.Equal(this._agent.Id, result.AgentId);
        Assert.Equal("task-789", result.ResponseId);
        Assert.Null(result.FinishReason);
        Assert.IsType<AgentTask>(result.RawRepresentation);
        Assert.Equal("task-789", ((AgentTask)result.RawRepresentation).Id);

        // Assert - verify continuation token is set for submitted task
        Assert.NotNull(result.ContinuationToken);
        Assert.IsType<A2AContinuationToken>(result.ContinuationToken);
        Assert.Equal("task-789", ((A2AContinuationToken)result.ContinuationToken).TaskId);

        // Assert - verify session is updated with context and task IDs
        var a2aSession = (A2AAgentSession)session;
        Assert.Equal("context-456", a2aSession.ContextId);
        Assert.Equal("task-789", a2aSession.TaskId);

        // Assert - verify metadata is preserved
        Assert.NotNull(result.AdditionalProperties);
        Assert.NotNull(result.AdditionalProperties["key1"]);
        Assert.Equal("value1", ((JsonElement)result.AdditionalProperties["key1"]!).GetString());
        Assert.NotNull(result.AdditionalProperties["count"]);
        Assert.Equal(42, ((JsonElement)result.AdditionalProperties["count"]!).GetInt32());
    }

    [Theory]
    [InlineData(TaskState.Submitted)]
    [InlineData(TaskState.Working)]
    [InlineData(TaskState.Completed)]
    [InlineData(TaskState.Failed)]
    [InlineData(TaskState.Canceled)]
    public async Task RunAsync_WithVariousTaskStates_ReturnsCorrectTokenAsync(TaskState taskState)
    {
        // Arrange
        this._handler.ResponseToReturn = new SendMessageResponse
        {
            Task = new AgentTask
            {
                Id = "task-123",
                ContextId = "context-123",
                Status = new() { State = taskState }
            }
        };

        // Act
        var result = await this._agent.RunAsync("Test message");

        // Assert
        if (taskState is TaskState.Submitted or TaskState.Working)
        {
            Assert.NotNull(result.ContinuationToken);
        }
        else
        {
            Assert.Null(result.ContinuationToken);
        }

        if (taskState is TaskState.Completed)
        {
            Assert.Equal(ChatFinishReason.Stop, result.FinishReason);
        }
        else
        {
            Assert.Null(result.FinishReason);
        }
    }

    [Fact]
    public async Task RunStreamingAsync_WithContinuationTokenAndMessages_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var options = new AgentRunOptions { ContinuationToken = new A2AContinuationToken("task-123") };

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in this._agent.RunStreamingAsync(inputMessages, null, options))
            {
                // Just iterate through to trigger the exception
            }
        });
    }

    [Fact]
    public async Task RunStreamingAsync_WithContinuationToken_UsesSubscribeToTaskMethodAsync()
    {
        // Arrange
        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Message = new Message
            {
                MessageId = "response-123",
                Role = Role.Agent,
                Parts = [new Part { Text = "Continuation response" }]
            }
        };

        var options = new AgentRunOptions { ContinuationToken = new A2AContinuationToken("task-456") };

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync([], null, options))
        {
            // Just iterate through to trigger the logic
        }

        // Assert - verify SubscribeToTask was called (not SendStreamingMessage)
        Assert.Single(this._handler.CapturedJsonRpcRequests);
        Assert.Equal("SubscribeToTask", this._handler.CapturedJsonRpcRequests[0].Method);
    }

    [Fact]
    public async Task RunStreamingAsync_WithContinuationToken_PassesCorrectTaskIdAsync()
    {
        // Arrange
        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Message = new Message
            {
                MessageId = "response-123",
                Role = Role.Agent,
                Parts = [new Part { Text = "Continuation response" }]
            }
        };

        const string ExpectedTaskId = "my-task-789";
        var options = new AgentRunOptions { ContinuationToken = new A2AContinuationToken(ExpectedTaskId) };

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync([], null, options))
        {
            // Just iterate through to trigger the logic
        }

        // Assert - verify the task ID was passed correctly
        Assert.NotEmpty(this._handler.CapturedJsonRpcRequests);
        var subscribeRequest = this._handler.CapturedJsonRpcRequests[0];
        var subscribeParams = subscribeRequest.Params?.Deserialize<SubscribeToTaskRequest>(A2AJsonUtilities.DefaultOptions);
        Assert.NotNull(subscribeParams);
        Assert.Equal(ExpectedTaskId, subscribeParams.Id);
    }

    [Fact]
    public async Task RunStreamingAsync_WithContinuationToken_WhenSubscribeFailsWithUnsupportedOperation_FallsBackToGetTaskAsync()
    {
        // Arrange
        const string TaskId = "completed-task-123";
        const string ContextId = "ctx-completed";

        this._handler.StreamingErrorCodeToReturn = A2AErrorCode.UnsupportedOperation;
        this._handler.AgentTaskToReturn = new AgentTask
        {
            Id = TaskId,
            ContextId = ContextId,
            Status = new() { State = TaskState.Completed },
            Artifacts =
            [
                new() { ArtifactId = "art-1", Parts = [new Part { Text = "Final result" }] }
            ]
        };

        var options = new AgentRunOptions { ContinuationToken = new A2AContinuationToken(TaskId) };

        // Act
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in this._agent.RunStreamingAsync([], null, options))
        {
            updates.Add(update);
        }

        // Assert - should yield one update from GetTaskAsync fallback
        Assert.Single(updates);
        var update0 = updates[0];
        Assert.Equal(TaskId, update0.ResponseId);
        Assert.Equal(ChatFinishReason.Stop, update0.FinishReason);
        Assert.IsType<AgentTask>(update0.RawRepresentation);
        Assert.Equal(TaskId, ((AgentTask)update0.RawRepresentation!).Id);

        // Assert - both SubscribeToTask and GetTask were called
        Assert.Equal(2, this._handler.CapturedJsonRpcRequests.Count);
        Assert.Equal("SubscribeToTask", this._handler.CapturedJsonRpcRequests[0].Method);
        Assert.Equal("GetTask", this._handler.CapturedJsonRpcRequests[1].Method);
    }

    [Fact]
    public async Task RunStreamingAsync_WithContinuationToken_WhenSubscribeFailsWithUnsupportedOperation_UpdatesSessionAsync()
    {
        // Arrange
        const string TaskId = "completed-task-456";
        const string ContextId = "ctx-completed-456";

        this._handler.StreamingErrorCodeToReturn = A2AErrorCode.UnsupportedOperation;
        this._handler.AgentTaskToReturn = new AgentTask
        {
            Id = TaskId,
            ContextId = ContextId,
            Status = new() { State = TaskState.Completed }
        };

        var session = await this._agent.CreateSessionAsync();
        var options = new AgentRunOptions { ContinuationToken = new A2AContinuationToken(TaskId) };

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync([], session, options))
        {
            // Just iterate through to trigger the logic
        }

        // Assert - session should be updated with the task state from GetTaskAsync
        var a2aSession = (A2AAgentSession)session;
        Assert.Equal(ContextId, a2aSession.ContextId);
        Assert.Equal(TaskId, a2aSession.TaskId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithContinuationToken_WhenSubscribeFailsWithNonUnsupportedError_PropagatesWithoutFallbackAsync()
    {
        // Arrange
        const string TaskId = "error-task-123";

        this._handler.StreamingErrorCodeToReturn = A2AErrorCode.TaskNotFound;

        var options = new AgentRunOptions { ContinuationToken = new A2AContinuationToken(TaskId) };

        // Act & Assert - the A2AException should propagate directly without fallback to GetTask
        var exception = await Assert.ThrowsAsync<A2AException>(async () =>
        {
            await foreach (var _ in this._agent.RunStreamingAsync([], null, options))
            {
            }
        });

        Assert.Equal(A2AErrorCode.TaskNotFound, exception.ErrorCode);

        // Assert - only SubscribeToTask was called, no fallback to GetTask
        Assert.Single(this._handler.CapturedJsonRpcRequests);
        Assert.Equal("SubscribeToTask", this._handler.CapturedJsonRpcRequests[0].Method);
    }

    [Fact]
    public async Task RunStreamingAsync_WithContinuationToken_WhenSubscribeAndGetTaskBothFail_PropagatesExceptionAsync()
    {
        // Arrange
        const string TaskId = "failed-task-789";

        this._handler.StreamingErrorCodeToReturn = A2AErrorCode.UnsupportedOperation;
        this._handler.GetTaskErrorCodeToReturn = A2AErrorCode.TaskNotFound;

        var options = new AgentRunOptions { ContinuationToken = new A2AContinuationToken(TaskId) };

        // Act & Assert - the A2AException from GetTaskAsync should propagate to the caller
        var exception = await Assert.ThrowsAsync<A2AException>(async () =>
        {
            await foreach (var _ in this._agent.RunStreamingAsync([], null, options))
            {
            }
        });

        Assert.Equal(A2AErrorCode.TaskNotFound, exception.ErrorCode);

        // Assert - both SubscribeToTask and GetTask were called
        Assert.Equal(2, this._handler.CapturedJsonRpcRequests.Count);
        Assert.Equal("SubscribeToTask", this._handler.CapturedJsonRpcRequests[0].Method);
        Assert.Equal("GetTask", this._handler.CapturedJsonRpcRequests[1].Method);
    }

    [Fact]
    public async Task RunStreamingAsync_WithTaskInSessionAndMessage_AddTaskAsReferencesToMessageAsync()
    {
        // Arrange
        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Message = new Message
            {
                MessageId = "response-123",
                Role = Role.Agent,
                Parts = [new Part { Text = "Response to task" }]
            }
        };

        var session = (A2AAgentSession)await this._agent.CreateSessionAsync();
        session.TaskId = "task-123";

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync("Please make the background transparent", session))
        {
            // Just iterate through to trigger the logic
        }

        // Assert
        var message = this._handler.CapturedSendMessageRequest?.Message;
        Assert.Null(message?.TaskId);
        Assert.NotNull(message?.ReferenceTaskIds);
        Assert.Contains("task-123", message.ReferenceTaskIds);
    }

    [Fact]
    public async Task RunStreamingAsync_WithAgentTask_UpdatesSessionTaskIdAsync()
    {
        // Arrange
        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Task = new AgentTask
            {
                Id = "task-456",
                ContextId = "context-789",
                Status = new() { State = TaskState.Submitted }
            }
        };

        var session = await this._agent.CreateSessionAsync();

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync("Start a task", session))
        {
            // Just iterate through to trigger the logic
        }

        // Assert
        var a2aSession = (A2AAgentSession)session;
        Assert.Equal("task-456", a2aSession.TaskId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithAgentMessage_YieldsResponseUpdateAsync()
    {
        // Arrange
        const string MessageId = "msg-123";
        const string ContextId = "ctx-456";
        const string MessageText = "Hello from agent!";

        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Message = new Message
            {
                MessageId = MessageId,
                Role = Role.Agent,
                ContextId = ContextId,
                Parts =
                [
                    new Part { Text = MessageText }
                ]
            }
        };

        // Act
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in this._agent.RunStreamingAsync("Test message"))
        {
            updates.Add(update);
        }

        // Assert - one update should be yielded
        Assert.Single(updates);

        var update0 = updates[0];
        Assert.Equal(ChatRole.Assistant, update0.Role);
        Assert.Equal(MessageId, update0.MessageId);
        Assert.Equal(MessageId, update0.ResponseId);
        Assert.Equal(this._agent.Id, update0.AgentId);
        Assert.Equal(MessageText, update0.Text);
        Assert.Equal(ChatFinishReason.Stop, update0.FinishReason);
        Assert.IsType<Message>(update0.RawRepresentation);
        Assert.Equal(MessageId, ((Message)update0.RawRepresentation!).MessageId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithAgentTask_YieldsResponseUpdateAsync()
    {
        // Arrange
        const string TaskId = "task-789";
        const string ContextId = "ctx-012";

        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Task = new AgentTask
            {
                Id = TaskId,
                ContextId = ContextId,
                Status = new() { State = TaskState.Submitted },
                Artifacts = [
                new()
                {
                    ArtifactId = "art-123",
                    Parts = [new Part { Text = "Task artifact content" }]
                }
            ]
            }
        };

        var session = await this._agent.CreateSessionAsync();

        // Act
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in this._agent.RunStreamingAsync("Start long-running task", session))
        {
            updates.Add(update);
        }

        // Assert - one update should be yielded from artifact
        Assert.Single(updates);

        var update0 = updates[0];
        Assert.Equal(ChatRole.Assistant, update0.Role);
        Assert.Equal(TaskId, update0.ResponseId);
        Assert.Equal(this._agent.Id, update0.AgentId);
        Assert.Null(update0.FinishReason);
        Assert.IsType<AgentTask>(update0.RawRepresentation);
        Assert.Equal(TaskId, ((AgentTask)update0.RawRepresentation!).Id);

        // Assert - session should be updated with context and task IDs
        var a2aSession = (A2AAgentSession)session;
        Assert.Equal(ContextId, a2aSession.ContextId);
        Assert.Equal(TaskId, a2aSession.TaskId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithTaskStatusUpdateEvent_YieldsResponseUpdateAsync()
    {
        // Arrange
        const string TaskId = "task-status-123";
        const string ContextId = "ctx-status-456";

        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            StatusUpdate = new TaskStatusUpdateEvent
            {
                TaskId = TaskId,
                ContextId = ContextId,
                Status = new() { State = TaskState.Working }
            }
        };

        var session = await this._agent.CreateSessionAsync();

        // Act
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in this._agent.RunStreamingAsync("Check task status", session))
        {
            updates.Add(update);
        }

        // Assert - one update should be yielded
        Assert.Single(updates);

        var update0 = updates[0];
        Assert.Equal(ChatRole.Assistant, update0.Role);
        Assert.Equal(TaskId, update0.ResponseId);
        Assert.Equal(this._agent.Id, update0.AgentId);
        Assert.Null(update0.FinishReason);
        Assert.IsType<TaskStatusUpdateEvent>(update0.RawRepresentation);

        // Assert - session should be updated with context and task IDs
        var a2aSession = (A2AAgentSession)session;
        Assert.Equal(ContextId, a2aSession.ContextId);
        Assert.Equal(TaskId, a2aSession.TaskId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithTaskArtifactUpdateEvent_YieldsResponseUpdateAsync()
    {
        // Arrange
        const string TaskId = "task-artifact-123";
        const string ContextId = "ctx-artifact-456";
        const string ArtifactContent = "Task artifact data";

        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            ArtifactUpdate = new TaskArtifactUpdateEvent
            {
                TaskId = TaskId,
                ContextId = ContextId,
                Artifact = new()
                {
                    ArtifactId = "artifact-789",
                    Parts = [new Part { Text = ArtifactContent }]
                }
            }
        };

        var session = await this._agent.CreateSessionAsync();

        // Act
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in this._agent.RunStreamingAsync("Process artifact", session))
        {
            updates.Add(update);
        }

        // Assert - one update should be yielded
        Assert.Single(updates);

        var update0 = updates[0];
        Assert.Equal(ChatRole.Assistant, update0.Role);
        Assert.Equal(TaskId, update0.ResponseId);
        Assert.Equal(this._agent.Id, update0.AgentId);
        Assert.Null(update0.FinishReason);
        Assert.IsType<TaskArtifactUpdateEvent>(update0.RawRepresentation);

        // Assert - artifact content should be in the update
        Assert.NotEmpty(update0.Contents);
        Assert.Equal(ArtifactContent, update0.Text);

        // Assert - session should be updated with context and task IDs
        var a2aSession = (A2AAgentSession)session;
        Assert.Equal(ContextId, a2aSession.ContextId);
        Assert.Equal(TaskId, a2aSession.TaskId);
    }

    [Fact]
    public async Task RunAsync_WithAllowBackgroundResponsesAndNoSession_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var options = new AgentRunOptions { AllowBackgroundResponses = true };

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => this._agent.RunAsync(inputMessages, null, options));
    }

    [Fact]
    public async Task RunStreamingAsync_WithAllowBackgroundResponsesAndNoSession_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var options = new AgentRunOptions { AllowBackgroundResponses = true };

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in this._agent.RunStreamingAsync(inputMessages, null, options))
            {
                // Just iterate through to trigger the exception
            }
        });
    }

    [Fact]
    public async Task RunAsync_WithAgentMessageResponseMetadata_ReturnsMetadataAsAdditionalPropertiesAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new SendMessageResponse
        {
            Message = new Message
            {
                MessageId = "response-123",
                Role = Role.Agent,
                Parts = [new Part { Text = "Response with metadata" }],
                Metadata = new Dictionary<string, JsonElement>
                {
                    { "responseKey1", JsonSerializer.SerializeToElement("responseValue1") },
                    { "responseCount", JsonSerializer.SerializeToElement(99) }
                }
            }
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Act
        var result = await this._agent.RunAsync(inputMessages);

        // Assert
        Assert.NotNull(result.AdditionalProperties);
        Assert.NotNull(result.AdditionalProperties["responseKey1"]);
        Assert.Equal("responseValue1", ((JsonElement)result.AdditionalProperties["responseKey1"]!).GetString());
        Assert.NotNull(result.AdditionalProperties["responseCount"]);
        Assert.Equal(99, ((JsonElement)result.AdditionalProperties["responseCount"]!).GetInt32());
    }

    [Fact]
    public async Task RunAsync_WithAdditionalProperties_PropagatesThemAsMetadataToSendMessageRequestAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new SendMessageResponse
        {
            Message = new Message
            {
                MessageId = "response-123",
                Role = Role.Agent,
                Parts = [new Part { Text = "Response" }]
            }
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var options = new AgentRunOptions
        {
            AdditionalProperties = new()
            {
                { "key1", "value1" },
                { "key2", 42 },
                { "key3", true }
            }
        };

        // Act
        await this._agent.RunAsync(inputMessages, null, options);

        // Assert
        Assert.NotNull(this._handler.CapturedSendMessageRequest);
        Assert.NotNull(this._handler.CapturedSendMessageRequest.Metadata);
        Assert.Equal("value1", this._handler.CapturedSendMessageRequest.Metadata["key1"].GetString());
        Assert.Equal(42, this._handler.CapturedSendMessageRequest.Metadata["key2"].GetInt32());
        Assert.True(this._handler.CapturedSendMessageRequest.Metadata["key3"].GetBoolean());
    }

    [Fact]
    public async Task RunAsync_WithNullAdditionalProperties_DoesNotSetMetadataAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new SendMessageResponse
        {
            Message = new Message
            {
                MessageId = "response-123",
                Role = Role.Agent,
                Parts = [new Part { Text = "Response" }]
            }
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var options = new AgentRunOptions
        {
            AdditionalProperties = null
        };

        // Act
        await this._agent.RunAsync(inputMessages, null, options);

        // Assert
        Assert.NotNull(this._handler.CapturedSendMessageRequest);
        Assert.Null(this._handler.CapturedSendMessageRequest.Metadata);
    }

    [Fact]
    public async Task RunStreamingAsync_WithAdditionalProperties_PropagatesThemAsMetadataToSendMessageRequestAsync()
    {
        // Arrange
        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Message = new Message
            {
                MessageId = "stream-123",
                Role = Role.Agent,
                Parts = [new Part { Text = "Streaming response" }]
            }
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test streaming message")
        };

        var options = new AgentRunOptions
        {
            AdditionalProperties = new()
            {
                { "streamKey1", "streamValue1" },
                { "streamKey2", 100 },
                { "streamKey3", false }
            }
        };

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync(inputMessages, null, options))
        {
        }

        // Assert
        Assert.NotNull(this._handler.CapturedSendMessageRequest);
        Assert.NotNull(this._handler.CapturedSendMessageRequest.Metadata);
        Assert.Equal("streamValue1", this._handler.CapturedSendMessageRequest.Metadata["streamKey1"].GetString());
        Assert.Equal(100, this._handler.CapturedSendMessageRequest.Metadata["streamKey2"].GetInt32());
        Assert.False(this._handler.CapturedSendMessageRequest.Metadata["streamKey3"].GetBoolean());
    }

    [Fact]
    public async Task RunStreamingAsync_WithNullAdditionalProperties_DoesNotSetMetadataAsync()
    {
        // Arrange
        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Message = new Message
            {
                MessageId = "stream-123",
                Role = Role.Agent,
                Parts = [new Part { Text = "Streaming response" }]
            }
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test streaming message")
        };

        var options = new AgentRunOptions
        {
            AdditionalProperties = null
        };

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync(inputMessages, null, options))
        {
        }

        // Assert
        Assert.NotNull(this._handler.CapturedSendMessageRequest);
        Assert.Null(this._handler.CapturedSendMessageRequest.Metadata);
    }

    [Fact]
    public async Task RunAsync_WithDefaultOptions_SetsBlockingToTrueAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Act
        await this._agent.RunAsync(inputMessages);

        // Assert
        Assert.NotNull(this._handler.CapturedSendMessageRequest);
        Assert.NotNull(this._handler.CapturedSendMessageRequest.Configuration);
        Assert.False(this._handler.CapturedSendMessageRequest.Configuration.ReturnImmediately);
    }

    [Fact]
    public async Task RunAsync_WithAllowBackgroundResponsesTrue_SetsReturnImmediatelyToTrueAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var session = await this._agent.CreateSessionAsync();
        var options = new AgentRunOptions { AllowBackgroundResponses = true };

        // Act
        await this._agent.RunAsync(inputMessages, session, options);

        // Assert
        Assert.NotNull(this._handler.CapturedSendMessageRequest);
        Assert.NotNull(this._handler.CapturedSendMessageRequest.Configuration);
        Assert.True(this._handler.CapturedSendMessageRequest.Configuration.ReturnImmediately);
    }

    [Fact]
    public async Task RunAsync_WithAllowBackgroundResponsesFalse_SetsReturnImmediatelyToFalseAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var options = new AgentRunOptions { AllowBackgroundResponses = false };

        // Act
        await this._agent.RunAsync(inputMessages, null, options);

        // Assert
        Assert.NotNull(this._handler.CapturedSendMessageRequest);
        Assert.NotNull(this._handler.CapturedSendMessageRequest.Configuration);
        Assert.False(this._handler.CapturedSendMessageRequest.Configuration.ReturnImmediately);
    }

    [Fact]
    public async Task RunAsync_WithNullOptions_SetsReturnImmediatelyToFalseAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Act
        await this._agent.RunAsync(inputMessages, null, null);

        // Assert
        Assert.NotNull(this._handler.CapturedSendMessageRequest);
        Assert.NotNull(this._handler.CapturedSendMessageRequest.Configuration);
        Assert.False(this._handler.CapturedSendMessageRequest.Configuration.ReturnImmediately);
    }

    [Fact]
    public async Task RunStreamingAsync_SendMessageRequest_DoesNotSetReturnImmediatelyConfigurationAsync()
    {
        // Arrange
        this._handler.StreamingResponseToReturn = new StreamResponse
        {
            Message = new Message
            {
                MessageId = "response-123",
                Role = Role.Agent,
                Parts = [new Part { Text = "Streaming response" }]
            }
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync(inputMessages))
        {
            // Just iterate through to trigger the logic
        }

        // Assert
        Assert.NotNull(this._handler.CapturedSendMessageRequest);
        Assert.Null(this._handler.CapturedSendMessageRequest.Configuration);
    }

    [Fact]
    public async Task RunAsync_WithInvalidSessionType_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        // Create a session from a different agent type
        var invalidSession = new CustomAgentSession();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => this._agent.RunAsync(invalidSession));
    }

    [Fact]
    public async Task RunStreamingAsync_WithInvalidSessionType_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Create a session from a different agent type
        var invalidSession = new CustomAgentSession();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await this._agent.RunStreamingAsync(inputMessages, invalidSession).ToListAsync());
    }

    #region GetService Method Tests

    /// <summary>
    /// Verify that GetService returns IA2AClient when requested.
    /// </summary>
    [Fact]
    public void GetService_RequestingIA2AClient_ReturnsA2AClient()
    {
        // Arrange & Act
        var result = this._agent.GetService(typeof(IA2AClient));

        // Assert
        Assert.NotNull(result);
        Assert.Same(this._a2aClient, result);
    }

    /// <summary>
    /// Verify that GetService returns null when requesting the concrete A2AClient type
    /// since the agent now exposes IA2AClient instead.
    /// </summary>
    [Fact]
    public void GetService_RequestingConcreteA2AClient_ReturnsNull()
    {
        // Arrange & Act
        var result = this._agent.GetService(typeof(A2AClient));

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService returns AIAgentMetadata when requested.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentMetadata_ReturnsMetadata()
    {
        // Arrange & Act
        var result = this._agent.GetService(typeof(AIAgentMetadata));

        // Assert
        Assert.NotNull(result);
        Assert.IsType<AIAgentMetadata>(result);
        var metadata = (AIAgentMetadata)result;
        Assert.Equal("a2a", metadata.ProviderName);
    }

    /// <summary>
    /// Verify that GetService returns null for unknown service types.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnknownServiceType_ReturnsNull()
    {
        // Arrange & Act
        var result = this._agent.GetService(typeof(string));

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService with serviceKey parameter returns null for unknown service types.
    /// </summary>
    [Fact]
    public void GetService_WithServiceKey_ReturnsNull()
    {
        // Arrange & Act
        var result = this._agent.GetService(typeof(string), "test-key");

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first and returns the agent itself when requesting A2AAgent type.
    /// </summary>
    [Fact]
    public void GetService_RequestingA2AAgentType_ReturnsBaseImplementation()
    {
        // Arrange & Act
        var result = this._agent.GetService(typeof(A2AAgent));

        // Assert
        Assert.NotNull(result);
        Assert.Same(this._agent, result);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first and returns the agent itself when requesting AIAgent type.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentType_ReturnsBaseImplementation()
    {
        // Arrange & Act
        var result = this._agent.GetService(typeof(AIAgent));

        // Assert
        Assert.NotNull(result);
        Assert.Same(this._agent, result);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first but continues to derived logic when base returns null.
    /// </summary>
    [Fact]
    public void GetService_RequestingIA2AClientWithServiceKey_CallsBaseFirstThenDerivedLogic()
    {
        // Arrange & Act - Request IA2AClient with a service key (base.GetService will return null due to serviceKey)
        var result = this._agent.GetService(typeof(IA2AClient), "some-key");

        // Assert
        Assert.NotNull(result);
        Assert.Same(this._a2aClient, result);
    }

    /// <summary>
    /// Verify that GetService returns consistent AIAgentMetadata across multiple calls.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentMetadata_ReturnsConsistentMetadata()
    {
        // Arrange & Act
        var result1 = this._agent.GetService(typeof(AIAgentMetadata));
        var result2 = this._agent.GetService(typeof(AIAgentMetadata));

        // Assert
        Assert.NotNull(result1);
        Assert.NotNull(result2);
        Assert.Same(result1, result2); // Should return the same instance
        Assert.IsType<AIAgentMetadata>(result1);
        var metadata = (AIAgentMetadata)result1;
        Assert.Equal("a2a", metadata.ProviderName);
    }

    /// <summary>
    /// Verify that CreateSessionAsync with contextId creates a session with the correct context ID.
    /// </summary>
    [Fact]
    public async Task CreateSessionAsync_WithContextId_CreatesSessionWithContextIdAsync()
    {
        // Arrange
        const string ContextId = "test-context-123";

        // Act
        var session = await this._agent.CreateSessionAsync(ContextId);

        // Assert
        Assert.NotNull(session);
        Assert.IsType<A2AAgentSession>(session);
        var typedSession = (A2AAgentSession)session;
        Assert.Equal(ContextId, typedSession.ContextId);
        Assert.Null(typedSession.TaskId);
    }

    /// <summary>
    /// Verify that CreateSessionAsync with contextId and taskId creates a session with both IDs set correctly.
    /// </summary>
    [Fact]
    public async Task CreateSessionAsync_WithContextIdAndTaskId_CreatesSessionWithBothIdsAsync()
    {
        // Arrange
        const string ContextId = "test-context-456";
        const string TaskId = "test-task-789";

        // Act
        var session = await this._agent.CreateSessionAsync(ContextId, TaskId);

        // Assert
        Assert.NotNull(session);
        Assert.IsType<A2AAgentSession>(session);
        var typedSession = (A2AAgentSession)session;
        Assert.Equal(ContextId, typedSession.ContextId);
        Assert.Equal(TaskId, typedSession.TaskId);
    }

    /// <summary>
    /// Verify that CreateSessionAsync throws when contextId is null, empty, or whitespace.
    /// </summary>
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("\t")]
    [InlineData("\r\n")]
    public async Task CreateSessionAsync_WithInvalidContextId_ThrowsArgumentExceptionAsync(string? contextId)
    {
        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(async () =>
            await this._agent.CreateSessionAsync(contextId!));
    }

    /// <summary>
    /// Verify that CreateSessionAsync with both parameters throws when contextId is null, empty, or whitespace.
    /// </summary>
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("\t")]
    [InlineData("\r\n")]
    public async Task CreateSessionAsync_WithInvalidContextIdAndValidTaskId_ThrowsArgumentExceptionAsync(string? contextId)
    {
        // Arrange
        const string TaskId = "valid-task-id";

        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(async () =>
            await this._agent.CreateSessionAsync(contextId!, TaskId));
    }

    /// <summary>
    /// Verify that CreateSessionAsync with both parameters throws when taskId is null, empty, or whitespace.
    /// </summary>
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("\t")]
    [InlineData("\r\n")]
    public async Task CreateSessionAsync_WithValidContextIdAndInvalidTaskId_ThrowsArgumentExceptionAsync(string? taskId)
    {
        // Arrange
        const string ContextId = "valid-context-id";

        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(async () =>
            await this._agent.CreateSessionAsync(ContextId, taskId!));
    }
    #endregion

    public void Dispose()
    {
        this._a2aClient.Dispose();
        this._handler.Dispose();
        this._httpClient.Dispose();
    }

    /// <summary>
    /// Custom agent session class for testing invalid session type scenario.
    /// </summary>
    private sealed class CustomAgentSession : AgentSession;

    internal sealed class A2AClientHttpMessageHandlerStub : HttpMessageHandler
    {
        public JsonRpcRequest? CapturedJsonRpcRequest { get; set; }

        public List<JsonRpcRequest> CapturedJsonRpcRequests { get; } = [];

        public SendMessageRequest? CapturedSendMessageRequest { get; set; }

        public GetTaskRequest? CapturedGetTaskRequest { get; set; }

        public SendMessageResponse? ResponseToReturn { get; set; }

        public AgentTask? AgentTaskToReturn { get; set; }

        public StreamResponse? StreamingResponseToReturn { get; set; }

        /// <summary>
        /// When set, streaming requests for SubscribeToTask will return a JSON-RPC error
        /// with this error code. Used to simulate UnsupportedOperation errors.
        /// </summary>
        public A2AErrorCode? StreamingErrorCodeToReturn { get; set; }

        /// <summary>
        /// Error message to include when <see cref="StreamingErrorCodeToReturn"/> is set.
        /// </summary>
        public string StreamingErrorMessage { get; set; } = "Task is in a terminal state and cannot be subscribed to.";

        /// <summary>
        /// When set, GetTask requests will return a JSON-RPC error with this error code.
        /// Used to simulate failures in the GetTaskAsync fallback path.
        /// </summary>
        public A2AErrorCode? GetTaskErrorCodeToReturn { get; set; }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            // Capture the request content
#pragma warning disable CA2016 // Forward the 'CancellationToken' parameter to methods; overload doesn't exist downlevel
            var content = await request.Content!.ReadAsStringAsync();
#pragma warning restore CA2016

            this.CapturedJsonRpcRequest = JsonSerializer.Deserialize<JsonRpcRequest>(content);

            if (this.CapturedJsonRpcRequest is not null)
            {
                this.CapturedJsonRpcRequests.Add(this.CapturedJsonRpcRequest);
            }

            try
            {
                this.CapturedSendMessageRequest = this.CapturedJsonRpcRequest?.Params?.Deserialize<SendMessageRequest>(A2AJsonUtilities.DefaultOptions);
            }
            catch { /* Ignore deserialization errors for non-SendMessageRequest requests */ }

            try
            {
                this.CapturedGetTaskRequest = this.CapturedJsonRpcRequest?.Params?.Deserialize<GetTaskRequest>(A2AJsonUtilities.DefaultOptions);
            }
            catch { /* Ignore deserialization errors for non-GetTaskRequest requests */ }

            // Return a JSON-RPC error for GetTask when configured
            if (this.GetTaskErrorCodeToReturn is not null && this.CapturedJsonRpcRequest?.Method == "GetTask")
            {
                var jsonRpcResponse = new JsonRpcResponse
                {
                    Id = "response-id",
                    Error = new JsonRpcError
                    {
                        Code = (int)this.GetTaskErrorCodeToReturn.Value,
                        Message = "Simulated GetTask error."
                    }
                };

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(JsonSerializer.Serialize(jsonRpcResponse), Encoding.UTF8, "application/json")
                };
            }

            // Return the pre-configured AgentTask response (for tasks/get)
            if (this.AgentTaskToReturn is not null && this.CapturedJsonRpcRequest?.Method == "GetTask")
            {
                var jsonRpcResponse = new JsonRpcResponse
                {
                    Id = "response-id",
                    Result = JsonSerializer.SerializeToNode(this.AgentTaskToReturn, A2AJsonUtilities.DefaultOptions)
                };

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(JsonSerializer.Serialize(jsonRpcResponse), Encoding.UTF8, "application/json")
                };
            }

            // Return the pre-configured non-streaming response
            if (this.ResponseToReturn is not null)
            {
                var jsonRpcResponse = new JsonRpcResponse
                {
                    Id = "response-id",
                    Result = JsonSerializer.SerializeToNode(this.ResponseToReturn, A2AJsonUtilities.DefaultOptions)
                };

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(JsonSerializer.Serialize(jsonRpcResponse), Encoding.UTF8, "application/json")
                };
            }
            // Return a streaming JSON-RPC error (e.g., UnsupportedOperation for SubscribeToTask)
            else if (this.StreamingErrorCodeToReturn is not null
                     && this.CapturedJsonRpcRequest?.Method is "SubscribeToTask")
            {
                var jsonRpcResponse = new JsonRpcResponse
                {
                    Id = "response-id",
                    Error = new JsonRpcError
                    {
                        Code = (int)this.StreamingErrorCodeToReturn.Value,
                        Message = this.StreamingErrorMessage
                    }
                };

                var stream = new MemoryStream();
                using (var writer = new StreamWriter(stream, Encoding.UTF8, leaveOpen: true))
                {
                    await writer.WriteAsync($"data: {JsonSerializer.Serialize(jsonRpcResponse, A2AJsonUtilities.DefaultOptions)}\n\n");
#pragma warning disable CA2016 // Forward the 'CancellationToken' parameter to methods; overload doesn't exist downlevel
                    await writer.FlushAsync();
#pragma warning restore CA2016
                }

                stream.Position = 0;

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StreamContent(stream)
                    {
                        Headers = { { "Content-Type", "text/event-stream" } }
                    }
                };
            }
            // Return the pre-configured streaming response
            else if (this.StreamingResponseToReturn is not null)
            {
                var jsonRpcResponse = new JsonRpcResponse
                {
                    Id = "response-id",
                    Result = JsonSerializer.SerializeToNode(this.StreamingResponseToReturn, A2AJsonUtilities.DefaultOptions)
                };

                var stream = new MemoryStream();
                using (var writer = new StreamWriter(stream, Encoding.UTF8, leaveOpen: true))
                {
                    await writer.WriteAsync($"data: {JsonSerializer.Serialize(jsonRpcResponse, A2AJsonUtilities.DefaultOptions)}\n\n");
#pragma warning disable CA2016 // Forward the 'CancellationToken' parameter to methods; overload doesn't exist downlevel
                    await writer.FlushAsync();
#pragma warning restore CA2016
                }

                stream.Position = 0;

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StreamContent(stream)
                    {
                        Headers = { { "Content-Type", "text/event-stream" } }
                    }
                };
            }
            else
            {
                var jsonRpcResponse = new JsonRpcResponse
                {
                    Id = "response-id",
                    Result = JsonSerializer.SerializeToNode(new SendMessageResponse { Message = new Message() }, A2AJsonUtilities.DefaultOptions)
                };

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(JsonSerializer.Serialize(jsonRpcResponse), Encoding.UTF8, "application/json")
                };
            }
        }
    }
}
