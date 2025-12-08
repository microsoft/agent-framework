// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.ServerSentEvents;
using System.Text;
using System.Text.Encodings.Web;
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
        const string TestDisplayName = "test-display-name";

        // Act
        var agent = new A2AAgent(this._a2aClient, TestId, TestName, TestDescription, TestDisplayName);

        // Assert
        Assert.Equal(TestId, agent.Id);
        Assert.Equal(TestName, agent.Name);
        Assert.Equal(TestDescription, agent.Description);
        Assert.Equal(TestDisplayName, agent.DisplayName);
    }

    [Fact]
    public void Constructor_WithNullA2AClient_ThrowsArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new A2AAgent(null!));

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
        Assert.Equal(agent.Id, agent.DisplayName);
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
        this._handler.ResponseToReturn = new AgentMessage
        {
            MessageId = "response-123",
            Role = MessageRole.Agent,
            Parts =
            [
                new TextPart { Text = "Hello! How can I help you today?" }
            ]
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello, world!")
        };

        // Act
        var result = await this._agent.RunAsync(inputMessages);

        // Assert input message sent to A2AClient
        var inputMessage = this._handler.CapturedMessageSendParams?.Message;
        Assert.NotNull(inputMessage);
        Assert.Single(inputMessage.Parts);
        Assert.Equal(MessageRole.User, inputMessage.Role);
        Assert.Equal("Hello, world!", ((TextPart)inputMessage.Parts[0]).Text);

        // Assert response from A2AClient is converted correctly
        Assert.NotNull(result);
        Assert.Equal(this._agent.Id, result.AgentId);
        Assert.Equal("response-123", result.ResponseId);

        Assert.NotNull(result.RawRepresentation);
        Assert.IsType<AgentMessage>(result.RawRepresentation);
        Assert.Equal("response-123", ((AgentMessage)result.RawRepresentation).MessageId);

        Assert.Single(result.Messages);
        Assert.Equal(ChatRole.Assistant, result.Messages[0].Role);
        Assert.Equal("Hello! How can I help you today?", result.Messages[0].Text);
    }

    [Fact]
    public async Task RunAsync_WithNewThread_UpdatesThreadConversationIdAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new AgentMessage
        {
            MessageId = "response-123",
            Role = MessageRole.Agent,
            Parts =
            [
                new TextPart { Text = "Response" }
            ],
            ContextId = "new-context-id"
        };

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var thread = this._agent.GetNewThread();

        // Act
        await this._agent.RunAsync(inputMessages, thread);

        // Assert
        Assert.IsType<A2AAgentThread>(thread);
        var a2aThread = (A2AAgentThread)thread;
        Assert.Equal("new-context-id", a2aThread.ContextId);
    }

    [Fact]
    public async Task RunAsync_WithExistingThread_SetConversationIdToMessageAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        var thread = this._agent.GetNewThread();
        var a2aThread = (A2AAgentThread)thread;
        a2aThread.ContextId = "existing-context-id";

        // Act
        await this._agent.RunAsync(inputMessages, thread);

        // Assert
        var message = this._handler.CapturedMessageSendParams?.Message;
        Assert.NotNull(message);
        Assert.Equal("existing-context-id", message.ContextId);
    }

    [Fact]
    public async Task RunAsync_WithThreadHavingDifferentContextId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        this._handler.ResponseToReturn = new AgentMessage
        {
            MessageId = "response-123",
            Role = MessageRole.Agent,
            Parts =
            [
                new TextPart { Text = "Response" }
            ],
            ContextId = "different-context"
        };

        var thread = this._agent.GetNewThread();
        var a2aThread = (A2AAgentThread)thread;
        a2aThread.ContextId = "existing-context-id";

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => this._agent.RunAsync(inputMessages, thread));
    }

    [Fact]
    public async Task RunStreamingAsync_WithValidUserMessage_YieldsAgentRunResponseUpdatesAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Hello, streaming!")
        };

        this._handler.StreamingResponseToReturn = new AgentMessage()
        {
            MessageId = "stream-1",
            Role = MessageRole.Agent,
            Parts = [new TextPart { Text = "Hello" }],
            ContextId = "stream-context"
        };

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in this._agent.RunStreamingAsync(inputMessages))
        {
            updates.Add(update);
        }

        // Assert
        Assert.Single(updates);

        // Assert input message sent to A2AClient
        var inputMessage = this._handler.CapturedMessageSendParams?.Message;
        Assert.NotNull(inputMessage);
        Assert.Single(inputMessage.Parts);
        Assert.Equal(MessageRole.User, inputMessage.Role);
        Assert.Equal("Hello, streaming!", ((TextPart)inputMessage.Parts[0]).Text);

        // Assert response from A2AClient is converted correctly
        Assert.Equal(ChatRole.Assistant, updates[0].Role);
        Assert.Equal("Hello", updates[0].Text);
        Assert.Equal("stream-1", updates[0].MessageId);
        Assert.Equal(this._agent.Id, updates[0].AgentId);
        Assert.Equal("stream-1", updates[0].ResponseId);

        Assert.NotNull(updates[0].RawRepresentation);
        Assert.IsType<AgentMessage>(updates[0].RawRepresentation);
        Assert.Equal("stream-1", ((AgentMessage)updates[0].RawRepresentation!).MessageId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithThread_UpdatesThreadConversationIdAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test streaming")
        };

        this._handler.StreamingResponseToReturn = new AgentMessage()
        {
            MessageId = "stream-1",
            Role = MessageRole.Agent,
            Parts = [new TextPart { Text = "Response" }],
            ContextId = "new-stream-context"
        };

        var thread = this._agent.GetNewThread();

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync(inputMessages, thread))
        {
            // Just iterate through to trigger the logic
        }

        // Assert
        var a2aThread = (A2AAgentThread)thread;
        Assert.Equal("new-stream-context", a2aThread.ContextId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithExistingThread_SetConversationIdToMessageAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test streaming")
        };

        this._handler.StreamingResponseToReturn = new AgentMessage();

        var thread = this._agent.GetNewThread();
        var a2aThread = (A2AAgentThread)thread;
        a2aThread.ContextId = "existing-context-id";

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync(inputMessages, thread))
        {
            // Just iterate through to trigger the logic
        }

        // Assert
        var message = this._handler.CapturedMessageSendParams?.Message;
        Assert.NotNull(message);
        Assert.Equal("existing-context-id", message.ContextId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithThreadHavingDifferentContextId_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var thread = this._agent.GetNewThread();
        var a2aThread = (A2AAgentThread)thread;
        a2aThread.ContextId = "existing-context-id";

        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test streaming")
        };

        this._handler.StreamingResponseToReturn = new AgentMessage()
        {
            MessageId = "stream-1",
            Role = MessageRole.Agent,
            Parts = [new TextPart { Text = "Response" }],
            ContextId = "different-context"
        };

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var update in this._agent.RunStreamingAsync(inputMessages, thread))
            {
            }
        });
    }

    [Fact]
    public async Task RunStreamingAsync_AllowsNonUserRoleMessagesAsync()
    {
        // Arrange
        this._handler.StreamingResponseToReturn = new AgentMessage()
        {
            MessageId = "stream-1",
            Role = MessageRole.Agent,
            Parts = [new TextPart { Text = "Response" }],
            ContextId = "new-stream-context"
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
        var message = this._handler.CapturedMessageSendParams?.Message;
        Assert.NotNull(message);
        Assert.Equal(2, message.Parts.Count);
        Assert.IsType<TextPart>(message.Parts[0]);
        Assert.Equal("Check this file:", ((TextPart)message.Parts[0]).Text);
        Assert.IsType<FilePart>(message.Parts[1]);
        Assert.Equal("https://example.com/file.pdf", ((FilePart)message.Parts[1]).File.Uri?.ToString());
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
        this._handler.ResponseToReturn = new AgentTask
        {
            Id = "task-123",
            ContextId = "context-123"
        };

        var options = new AgentRunOptions { ContinuationToken = new A2AContinuationToken("task-123") };

        // Act
        await this._agent.RunAsync([], options: options);

        // Assert
        Assert.Equal("tasks/get", this._handler.CapturedJsonRpcRequest?.Method);
        Assert.Equal("task-123", this._handler.CapturedTaskIdParams?.Id);
    }

    [Fact]
    public async Task RunAsync_WithTaskInThreadAndMessage_AddTaskAsReferencesToMessageAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new AgentMessage
        {
            MessageId = "response-123",
            Role = MessageRole.Agent,
            Parts = [new TextPart { Text = "Response to task" }]
        };

        var thread = (A2AAgentThread)this._agent.GetNewThread();
        thread.TaskId = "task-123";

        var inputMessage = new ChatMessage(ChatRole.User, "Please make the background transparent");

        // Act
        await this._agent.RunAsync(inputMessage, thread);

        // Assert
        var message = this._handler.CapturedMessageSendParams?.Message;
        Assert.Null(message?.TaskId);
        Assert.NotNull(message?.ReferenceTaskIds);
        Assert.Contains("task-123", message.ReferenceTaskIds);
    }

    [Fact]
    public async Task RunAsync_WithAgentTask_UpdatesThreadTaskIdAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new AgentTask
        {
            Id = "task-456",
            ContextId = "context-789",
            Status = new() { State = TaskState.Submitted }
        };

        var thread = this._agent.GetNewThread();

        // Act
        await this._agent.RunAsync("Start a task", thread);

        // Assert
        var a2aThread = (A2AAgentThread)thread;
        Assert.Equal("task-456", a2aThread.TaskId);
    }

    [Fact]
    public async Task RunAsync_WithAgentTaskResponse_ReturnsTaskResponseCorrectlyAsync()
    {
        // Arrange
        this._handler.ResponseToReturn = new AgentTask
        {
            Id = "task-789",
            ContextId = "context-456",
            Status = new() { State = TaskState.Submitted },
            Metadata = new Dictionary<string, JsonElement>
            {
                { "key1", JsonSerializer.SerializeToElement("value1") },
                { "count", JsonSerializer.SerializeToElement(42) }
            }
        };

        var thread = this._agent.GetNewThread();

        // Act
        var result = await this._agent.RunAsync("Start a long-running task", thread);

        // Assert - verify task is converted correctly
        Assert.NotNull(result);
        Assert.Equal(this._agent.Id, result.AgentId);
        Assert.Equal("task-789", result.ResponseId);

        Assert.NotNull(result.RawRepresentation);
        Assert.IsType<AgentTask>(result.RawRepresentation);
        Assert.Equal("task-789", ((AgentTask)result.RawRepresentation).Id);

        // Assert - verify continuation token is set for submitted task
        Assert.NotNull(result.ContinuationToken);
        Assert.IsType<A2AContinuationToken>(result.ContinuationToken);
        Assert.Equal("task-789", ((A2AContinuationToken)result.ContinuationToken).TaskId);

        // Assert - verify thread is updated with context and task IDs
        var a2aThread = (A2AAgentThread)thread;
        Assert.Equal("context-456", a2aThread.ContextId);
        Assert.Equal("task-789", a2aThread.TaskId);

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
        this._handler.ResponseToReturn = new AgentTask
        {
            Id = "task-123",
            ContextId = "context-123",
            Status = new() { State = taskState }
        };

        // Act
        var result = await this._agent.RunAsync("Test message");

        // Assert
        if (taskState == TaskState.Submitted || taskState == TaskState.Working)
        {
            Assert.NotNull(result.ContinuationToken);
        }
        else
        {
            Assert.Null(result.ContinuationToken);
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
    public async Task RunStreamingAsync_WithTaskInThreadAndMessage_AddTaskAsReferencesToMessageAsync()
    {
        // Arrange
        this._handler.StreamingResponseToReturn = new AgentMessage
        {
            MessageId = "response-123",
            Role = MessageRole.Agent,
            Parts = [new TextPart { Text = "Response to task" }]
        };

        var thread = (A2AAgentThread)this._agent.GetNewThread();
        thread.TaskId = "task-123";

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync("Please make the background transparent", thread))
        {
            // Just iterate through to trigger the logic
        }

        // Assert
        var message = this._handler.CapturedMessageSendParams?.Message;
        Assert.Null(message?.TaskId);
        Assert.NotNull(message?.ReferenceTaskIds);
        Assert.Contains("task-123", message.ReferenceTaskIds);
    }

    [Fact]
    public async Task RunStreamingAsync_WithAgentTask_UpdatesThreadTaskIdAsync()
    {
        // Arrange
        this._handler.StreamingResponseToReturn = new AgentTask
        {
            Id = "task-456",
            ContextId = "context-789",
            Status = new() { State = TaskState.Submitted }
        };

        var thread = this._agent.GetNewThread();

        // Act
        await foreach (var _ in this._agent.RunStreamingAsync("Start a task", thread))
        {
            // Just iterate through to trigger the logic
        }

        // Assert
        var a2aThread = (A2AAgentThread)thread;
        Assert.Equal("task-456", a2aThread.TaskId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithAgentMessage_YieldsResponseUpdateAsync()
    {
        // Arrange
        const string MessageId = "msg-123";
        const string ContextId = "ctx-456";
        const string MessageText = "Hello from agent!";

        this._handler.StreamingResponseToReturn = new AgentMessage
        {
            MessageId = MessageId,
            Role = MessageRole.Agent,
            ContextId = ContextId,
            Parts =
            [
                new TextPart { Text = MessageText }
            ]
        };

        // Act
        var updates = new List<AgentRunResponseUpdate>();
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
        Assert.IsType<AgentMessage>(update0.RawRepresentation);
        Assert.Equal(MessageId, ((AgentMessage)update0.RawRepresentation!).MessageId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithAgentTask_YieldsResponseUpdateAsync()
    {
        // Arrange
        const string TaskId = "task-789";
        const string ContextId = "ctx-012";

        this._handler.StreamingResponseToReturn = new AgentTask
        {
            Id = TaskId,
            ContextId = ContextId,
            Status = new() { State = TaskState.Submitted },
            Artifacts = [
                new()
                {
                    ArtifactId = "art-123",
                    Parts = [new TextPart { Text = "Task artifact content" }]
                }
            ]
        };

        var thread = this._agent.GetNewThread();

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in this._agent.RunStreamingAsync("Start long-running task", thread))
        {
            updates.Add(update);
        }

        // Assert - one update should be yielded from artifact
        Assert.Single(updates);

        var update0 = updates[0];
        Assert.Equal(ChatRole.Assistant, update0.Role);
        Assert.Equal(TaskId, update0.ResponseId);
        Assert.Equal(this._agent.Id, update0.AgentId);
        Assert.IsType<AgentTask>(update0.RawRepresentation);
        Assert.Equal(TaskId, ((AgentTask)update0.RawRepresentation!).Id);

        // Assert - thread should be updated with context and task IDs
        var a2aThread = (A2AAgentThread)thread;
        Assert.Equal(ContextId, a2aThread.ContextId);
        Assert.Equal(TaskId, a2aThread.TaskId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithTaskStatusUpdateEvent_YieldsResponseUpdateAsync()
    {
        // Arrange
        const string TaskId = "task-status-123";
        const string ContextId = "ctx-status-456";

        this._handler.StreamingResponseToReturn = new TaskStatusUpdateEvent
        {
            TaskId = TaskId,
            ContextId = ContextId,
            Status = new() { State = TaskState.Working }
        };

        var thread = this._agent.GetNewThread();

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in this._agent.RunStreamingAsync("Check task status", thread))
        {
            updates.Add(update);
        }

        // Assert - one update should be yielded
        Assert.Single(updates);

        var update0 = updates[0];
        Assert.Equal(ChatRole.Assistant, update0.Role);
        Assert.Equal(TaskId, update0.ResponseId);
        Assert.Equal(this._agent.Id, update0.AgentId);
        Assert.IsType<TaskStatusUpdateEvent>(update0.RawRepresentation);

        // Assert - thread should be updated with context and task IDs
        var a2aThread = (A2AAgentThread)thread;
        Assert.Equal(ContextId, a2aThread.ContextId);
        Assert.Equal(TaskId, a2aThread.TaskId);
    }

    [Fact]
    public async Task RunStreamingAsync_WithTaskArtifactUpdateEvent_YieldsResponseUpdateAsync()
    {
        // Arrange
        const string TaskId = "task-artifact-123";
        const string ContextId = "ctx-artifact-456";
        const string ArtifactContent = "Task artifact data";

        this._handler.StreamingResponseToReturn = new TaskArtifactUpdateEvent
        {
            TaskId = TaskId,
            ContextId = ContextId,
            Artifact = new()
            {
                ArtifactId = "artifact-789",
                Parts = [new TextPart { Text = ArtifactContent }]
            }
        };

        var thread = this._agent.GetNewThread();

        // Act
        var updates = new List<AgentRunResponseUpdate>();
        await foreach (var update in this._agent.RunStreamingAsync("Process artifact", thread))
        {
            updates.Add(update);
        }

        // Assert - one update should be yielded
        Assert.Single(updates);

        var update0 = updates[0];
        Assert.Equal(ChatRole.Assistant, update0.Role);
        Assert.Equal(TaskId, update0.ResponseId);
        Assert.Equal(this._agent.Id, update0.AgentId);
        Assert.IsType<TaskArtifactUpdateEvent>(update0.RawRepresentation);

        // Assert - artifact content should be in the update
        Assert.NotEmpty(update0.Contents);
        Assert.Equal(ArtifactContent, update0.Text);

        // Assert - thread should be updated with context and task IDs
        var a2aThread = (A2AAgentThread)thread;
        Assert.Equal(ContextId, a2aThread.ContextId);
        Assert.Equal(TaskId, a2aThread.TaskId);
    }

    [Fact]
    public async Task RunAsync_WithAllowBackgroundResponsesAndNoThread_ThrowsInvalidOperationExceptionAsync()
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
    public async Task RunStreamingAsync_WithAllowBackgroundResponsesAndNoThread_ThrowsInvalidOperationExceptionAsync()
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
    public async Task RunAsync_WithInvalidThreadType_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        // Create a thread from a different agent type
        var invalidThread = new CustomAgentThread();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => this._agent.RunAsync(invalidThread));
    }

    [Fact]
    public async Task RunStreamingAsync_WithInvalidThreadType_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var inputMessages = new List<ChatMessage>
        {
            new(ChatRole.User, "Test message")
        };

        // Create a thread from a different agent type
        var invalidThread = new CustomAgentThread();

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await this._agent.RunStreamingAsync(inputMessages, invalidThread).ToListAsync());
    }

    public void Dispose()
    {
        this._handler.Dispose();
        this._httpClient.Dispose();
    }

    /// <summary>
    /// Custom agent thread class for testing invalid thread type scenario.
    /// </summary>
    private sealed class CustomAgentThread : AgentThread;

    internal sealed class A2AClientHttpMessageHandlerStub : HttpMessageHandler
    {
        public JsonRpcRequest? CapturedJsonRpcRequest { get; set; }

        public MessageSendParams? CapturedMessageSendParams { get; set; }

        public TaskIdParams? CapturedTaskIdParams { get; set; }

        public A2AEvent? ResponseToReturn { get; set; }

        public A2AEvent? StreamingResponseToReturn { get; set; }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            // Capture the request content
#pragma warning disable CA2016 // Forward the 'CancellationToken' parameter to methods; overload doesn't exist downlevel
            var content = await request.Content!.ReadAsStringAsync();
#pragma warning restore CA2016

            this.CapturedJsonRpcRequest = JsonSerializer.Deserialize<JsonRpcRequest>(content);

            try
            {
                this.CapturedMessageSendParams = this.CapturedJsonRpcRequest?.Params?.Deserialize<MessageSendParams>();
            }
            catch { /* Ignore deserialization errors for non-MessageSendParams requests */ }

            try
            {
                this.CapturedTaskIdParams = this.CapturedJsonRpcRequest?.Params?.Deserialize<TaskIdParams>();
            }
            catch { /* Ignore deserialization errors for non-TaskIdParams requests */ }

            // Return the pre-configured non-streaming response
            if (this.ResponseToReturn is not null)
            {
                var jsonRpcResponse = JsonRpcResponse.CreateJsonRpcResponse("response-id", this.ResponseToReturn);

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(JsonSerializer.Serialize(jsonRpcResponse), Encoding.UTF8, "application/json")
                };
            }
            // Return the pre-configured streaming response
            else if (this.StreamingResponseToReturn is not null)
            {
                var stream = new MemoryStream();

                await SseFormatter.WriteAsync(
                    new SseItem<JsonRpcResponse>[]
                    {
                        new(JsonRpcResponse.CreateJsonRpcResponse("response-id", this.StreamingResponseToReturn!))
                    }.ToAsyncEnumerable(),
                    stream,
                    (item, writer) =>
                    {
                        using Utf8JsonWriter json = new(writer, new() { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
                        JsonSerializer.Serialize(json, item.Data);
                    },
                    cancellationToken
                );

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
                var jsonRpcResponse = JsonRpcResponse.CreateJsonRpcResponse<A2AEvent>("response-id", new AgentMessage());

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(JsonSerializer.Serialize(jsonRpcResponse), Encoding.UTF8, "application/json")
                };
            }
        }
    }
}
