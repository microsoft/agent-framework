// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="A2AAgentHandler"/> class.
/// </summary>
public sealed class A2AAgentHandlerTests
{
    /// <summary>
    /// Verifies that when metadata is null, the options passed to RunAsync have
    /// AllowBackgroundResponses disabled and no AdditionalProperties.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenMetadataIsNull_PassesOptionsWithNoAdditionalPropertiesToRunAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        A2AAgentHandler handler = CreateHandler(CreateAgentMock(options => capturedOptions = options));

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.False(capturedOptions.AllowBackgroundResponses);
        Assert.Null(capturedOptions.AdditionalProperties);
    }

    /// <summary>
    /// Verifies that when metadata is non-empty, the options passed to RunAsync have
    /// AdditionalProperties populated with the converted metadata values.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenMetadataIsNonEmpty_PassesOptionsWithAdditionalPropertiesToRunAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        A2AAgentHandler handler = CreateHandler(CreateAgentMock(options => capturedOptions = options));

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false,
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] },
            Metadata = new Dictionary<string, JsonElement>
            {
                ["key1"] = JsonSerializer.SerializeToElement("value1"),
                ["key2"] = JsonSerializer.SerializeToElement(42)
            }
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.False(capturedOptions.AllowBackgroundResponses);
        Assert.NotNull(capturedOptions.AdditionalProperties);
        Assert.Equal(2, capturedOptions.AdditionalProperties.Count);
        Assert.Equal("value1", capturedOptions.AdditionalProperties["key1"]?.ToString());
    }

    /// <summary>
    /// Verifies that when the agent response has AdditionalProperties, the returned Message.Metadata contains the converted values.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenResponseHasAdditionalProperties_ReturnsMessageWithMetadataAsync()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProps = new()
        {
            ["responseKey1"] = "responseValue1",
            ["responseKey2"] = 123
        };
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Test response")])
        {
            AdditionalProperties = additionalProps
        };
        A2AAgentHandler handler = CreateHandler(CreateAgentMockWithResponse(response));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.NotNull(message.Metadata);
        Assert.Equal(2, message.Metadata.Count);
        Assert.True(message.Metadata.ContainsKey("responseKey1"));
        Assert.True(message.Metadata.ContainsKey("responseKey2"));
    }

    /// <summary>
    /// Verifies that when the agent response has null AdditionalProperties, the returned Message.Metadata is null.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenResponseHasNullAdditionalProperties_ReturnsMessageWithNullMetadataAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Test response")])
        {
            AdditionalProperties = null
        };
        A2AAgentHandler handler = CreateHandler(CreateAgentMockWithResponse(response));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.Null(message.Metadata);
    }

    /// <summary>
    /// Verifies that when the agent response has empty AdditionalProperties, the returned Message.Metadata is null.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenResponseHasEmptyAdditionalProperties_ReturnsMessageWithNullMetadataAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Test response")])
        {
            AdditionalProperties = []
        };
        A2AAgentHandler handler = CreateHandler(CreateAgentMockWithResponse(response));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.Null(message.Metadata);
    }

    /// <summary>
    /// Verifies that when runMode is DisallowBackground, AllowBackgroundResponses is false.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_DisallowBackgroundMode_SetsAllowBackgroundResponsesFalseAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        A2AAgentHandler handler = CreateHandler(
            CreateAgentMock(options => capturedOptions = options),
            runMode: AgentRunMode.DisallowBackground);

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.False(capturedOptions.AllowBackgroundResponses);
    }

    /// <summary>
    /// Verifies that in AllowBackgroundIfSupported mode, AllowBackgroundResponses is true.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_AllowBackgroundIfSupportedMode_SetsAllowBackgroundResponsesTrueAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        A2AAgentHandler handler = CreateHandler(
            CreateAgentMock(options => capturedOptions = options),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.True(capturedOptions.AllowBackgroundResponses);
    }

    /// <summary>
    /// Verifies that a custom Dynamic delegate returning false sets AllowBackgroundResponses to false.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_DynamicMode_WithFalseCallback_SetsAllowBackgroundResponsesFalseAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        A2AAgentHandler handler = CreateHandler(
            CreateAgentMock(options => capturedOptions = options),
            runMode: AgentRunMode.AllowBackgroundWhen((_, _) => ValueTask.FromResult(false)));

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.False(capturedOptions.AllowBackgroundResponses);
    }

    /// <summary>
    /// Verifies that a custom Dynamic delegate returning true sets AllowBackgroundResponses to true.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_DynamicMode_WithTrueCallback_SetsAllowBackgroundResponsesTrueAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        A2AAgentHandler handler = CreateHandler(
            CreateAgentMock(options => capturedOptions = options),
            runMode: AgentRunMode.AllowBackgroundWhen((_, _) => ValueTask.FromResult(true)));

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.True(capturedOptions.AllowBackgroundResponses);
    }

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

    /// <summary>
    /// Verifies that when the agent returns a ContinuationToken, task status events are emitted.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenResponseHasContinuationToken_EmitsTaskStatusEventsAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Starting work...")])
        {
            ContinuationToken = CreateTestContinuationToken()
        };
        A2AAgentHandler handler = CreateHandler(CreateAgentMockWithResponse(response));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "task-1",
            ContextId = "ctx-1",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert - should have emitted status update events (Submitted + Working)
        Assert.True(events.StatusUpdates.Count >= 1);
        Assert.Empty(events.Messages);
    }

    /// <summary>
    /// Verifies that when the incoming message has a ContextId, it is used for the response
    /// rather than generating a new one.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenMessageHasContextId_UsesProvidedContextIdAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Reply")]);
        A2AAgentHandler handler = CreateHandler(CreateAgentMockWithResponse(response));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "",
            ContextId = "my-context-123",
            Message = new Message
            {
                MessageId = "test-id",
                ContextId = "my-context-123",
                Role = Role.User,
                Parts = [new Part { Text = "Hello" }]
            }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.Equal("my-context-123", message.ContextId);
    }

    /// <summary>
    /// Verifies that on continuation when the agent completes (no ContinuationToken), task is completed with artifact.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_OnContinuation_WhenComplete_EmitsArtifactAndCompletedAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Done!")]);
        A2AAgentHandler handler = CreateHandler(CreateAgentMockWithResponse(response));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            Message = new Message { MessageId = "empty", Role = Role.User, Parts = [] },
            TaskId = "task-1",
            ContextId = "ctx-1",

            Task = new AgentTask { Id = "task-1", ContextId = "ctx-1", History = [new Message { Role = Role.User, Parts = [new Part { Text = "Hello" }] }] }
        });

        // Assert - should have artifact + completed status
        Assert.True(events.ArtifactUpdates.Count > 0);
        Assert.True(events.StatusUpdates.Count > 0);
        Assert.Empty(events.Messages);
    }

    /// <summary>
    /// Verifies that when the agent throws during a continuation,
    /// the handler emits a Failed status and re-throws the exception.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_OnContinuation_WhenAgentThrows_EmitsFailedStatusAsync()
    {
        // Arrange
        int callCount = 0;
        Mock<AIAgent> agentMock = CreateAgentMockWithCallCount(ref callCount, _ =>
            throw new InvalidOperationException("Agent failed"));
        A2AAgentHandler handler = CreateHandler(agentMock);

        // Act & Assert
        var events = new EventCollector();
        var eventQueue = new AgentEventQueue();
        var readerTask = ReadEventsAsync(eventQueue, events);
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            handler.ExecuteAsync(
                new RequestContext
                {
                    StreamingResponse = false,
                    Message = new Message { MessageId = "empty", Role = Role.User, Parts = [] },
                    TaskId = "task-1",
                    ContextId = "ctx-1",

                    Task = new AgentTask { Id = "task-1", ContextId = "ctx-1", History = [new Message { Role = Role.User, Parts = [new Part { Text = "Hello" }] }] }
                },
                eventQueue,
                CancellationToken.None));
        eventQueue.Complete(null);
        await readerTask;

        // Assert - should have emitted Failed status
        Assert.True(events.StatusUpdates.Count > 0);
    }

    /// <summary>
    /// Verifies that when the agent throws during a continuation and the cancellation token
    /// is already cancelled, the handler still emits a Failed status and re-throws the
    /// original exception (not an OperationCanceledException from FailAsync).
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_OnContinuation_WhenAgentThrowsWithCancelledToken_StillEmitsFailedStatusAsync()
    {
        // Arrange
        int callCount = 0;
        Mock<AIAgent> agentMock = CreateAgentMockWithCallCount(ref callCount, _ =>
            throw new InvalidOperationException("Agent failed"));
        A2AAgentHandler handler = CreateHandler(agentMock);

        using var cts = new CancellationTokenSource();
        cts.Cancel(); // Pre-cancel the token

        // Act & Assert - the original InvalidOperationException should be thrown, not OperationCanceledException
        var events = new EventCollector();
        var eventQueue = new AgentEventQueue();
        var readerTask = ReadEventsAsync(eventQueue, events);
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            handler.ExecuteAsync(
                new RequestContext
                {
                    StreamingResponse = false,
                    Message = new Message { MessageId = "empty", Role = Role.User, Parts = [] },
                    TaskId = "task-1",
                    ContextId = "ctx-1",

                    Task = new AgentTask { Id = "task-1", ContextId = "ctx-1", History = [new Message { Role = Role.User, Parts = [new Part { Text = "Hello" }] }] }
                },
                eventQueue,
                cts.Token));
        eventQueue.Complete(null);
        await readerTask;

        // Assert - should have emitted Failed status even with a cancelled token
        Assert.True(events.StatusUpdates.Count > 0);
    }

    /// <summary>
    /// Verifies that when the agent throws OperationCanceledException during a continuation,
    /// no Failed status is emitted.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_OnContinuation_WhenOperationCancelled_DoesNotEmitFailedAsync()
    {
        // Arrange
        int callCount = 0;
        Mock<AIAgent> agentMock = CreateAgentMockWithCallCount(ref callCount, _ =>
            throw new OperationCanceledException("Cancelled"));
        A2AAgentHandler handler = CreateHandler(agentMock);

        // Act & Assert
        var events = new EventCollector();
        var eventQueue = new AgentEventQueue();
        var readerTask = ReadEventsAsync(eventQueue, events);
        await Assert.ThrowsAsync<OperationCanceledException>(() =>
            handler.ExecuteAsync(
                new RequestContext
                {
                    StreamingResponse = false,
                    Message = new Message { MessageId = "empty", Role = Role.User, Parts = [] },
                    TaskId = "task-1",
                    ContextId = "ctx-1",

                    Task = new AgentTask { Id = "task-1", ContextId = "ctx-1", History = [new Message { Role = Role.User, Parts = [new Part { Text = "Hello" }] }] }
                },
                eventQueue,
                CancellationToken.None));
        eventQueue.Complete(null);
        await readerTask;

        // Assert - should NOT have emitted any status (OperationCanceledException is re-thrown without marking Failed)
        Assert.Empty(events.StatusUpdates);
    }

    /// <summary>
    /// Verifies that ReferenceTaskIds throws NotSupportedException.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WithReferenceTaskIds_ThrowsNotSupportedExceptionAsync()
    {
        // Arrange
        A2AAgentHandler handler = CreateHandler(CreateAgentMock(_ => { }));

        // Act & Assert
        await Assert.ThrowsAsync<NotSupportedException>(() =>
            InvokeExecuteAsync(handler, new RequestContext
            {
                TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message
                {
                    MessageId = "test-id",
                    Role = Role.User,
                    Parts = [new Part { Text = "Hello" }],
                    ReferenceTaskIds = ["other-task-id"]
                }
            }));
    }

    /// <summary>
    /// Verifies that when ContextId is null, a new one is generated and used in the response.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenContextIdIsNull_GeneratesContextIdAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Reply")]);
        A2AAgentHandler handler = CreateHandler(CreateAgentMockWithResponse(response));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "",
            ContextId = null!,
            Message = new Message
            {
                MessageId = "test-id",
                Role = Role.User,
                Parts = [new Part { Text = "Hello" }]
            }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.NotNull(message.ContextId);
        Assert.NotEmpty(message.ContextId);
    }

    /// <summary>
    /// Verifies that when Message is null, the handler still succeeds with empty chat messages.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenMessageIsNull_SucceedsWithEmptyMessagesAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Reply")]);
        A2AAgentHandler handler = CreateHandler(CreateAgentMockWithResponse(response));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "",
            ContextId = "ctx",
            Message = null!
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.Equal("ctx", message.ContextId);
    }

    /// <summary>
    /// Verifies that the dynamic AllowBackgroundWhen delegate receives the correct RequestContext.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_DynamicMode_DelegateReceivesRequestContextAsync()
    {
        // Arrange
        A2ARunDecisionContext? capturedContext = null;
        A2AAgentHandler handler = CreateHandler(
            CreateAgentMock(_ => { }),
            runMode: AgentRunMode.AllowBackgroundWhen((ctx, _) =>
            {
                capturedContext = ctx;
                return ValueTask.FromResult(false);
            }));

        var requestContext = new RequestContext
        {
            TaskId = "my-task", ContextId = "my-ctx", StreamingResponse = false,
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        };

        // Act
        await InvokeExecuteAsync(handler, requestContext);

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Same(requestContext, capturedContext.RequestContext);
    }

    /// <summary>
    /// Verifies that CancelAsync emits a Canceled status event.
    /// </summary>
    [Fact]
    public async Task CancelAsync_EmitsCanceledStatusAsync()
    {
        // Arrange
        A2AAgentHandler handler = CreateHandler(CreateAgentMock(_ => { }));
        var events = new EventCollector();
        var eventQueue = new AgentEventQueue();
        var readerTask = ReadEventsAsync(eventQueue, events);

        // Act
        await handler.CancelAsync(
            new RequestContext
            {
                StreamingResponse = false,
                Message = new Message { MessageId = "empty", Role = Role.User, Parts = [] },
                TaskId = "task-1",
                ContextId = "ctx-1",
                Task = new AgentTask { Id = "task-1", ContextId = "ctx-1" }
            },
            eventQueue,
            CancellationToken.None);

        // Assert
        eventQueue.Complete(null);
        await readerTask;
        Assert.True(events.StatusUpdates.Count > 0);
    }

#pragma warning restore MEAI001

    /// <summary>
    /// Verifies that when no session store is provided, the handler uses InMemoryAgentSessionStore
    /// and can execute successfully.
    /// </summary>
    [Fact]
    public async Task Handler_WithNullSessionStore_UsesInMemorySessionStoreAndExecutesSuccessfullyAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Reply")]);
        A2AAgentHandler handler = CreateHandler(CreateAgentMockWithResponse(response), agentSessionStore: null);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "",
            ContextId = "ctx-1",
            Message = new Message
            {
                MessageId = "test-id",
                Role = Role.User,
                Parts = [new Part { Text = "Hello" }]
            }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.Equal("Reply", message.Parts![0].Text);
    }

    /// <summary>
    /// Verifies that when a custom session store is provided, it is used instead of the
    /// default InMemoryAgentSessionStore.
    /// </summary>
    [Fact]
    public async Task Handler_WithCustomSessionStore_UsesProvidedSessionStoreAsync()
    {
        // Arrange
        var mockSessionStore = new Mock<AgentSessionStore>();
        mockSessionStore
            .Setup(x => x.GetSessionAsync(
                It.IsAny<AIAgent>(),
                It.IsAny<string>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new TestAgentSession());
        mockSessionStore
            .Setup(x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.IsAny<string>(),
                It.IsAny<AgentSession>(),
                It.IsAny<CancellationToken>()))
            .Returns(ValueTask.CompletedTask);

        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Reply")]);
        A2AAgentHandler handler = CreateHandler(CreateAgentMockWithResponse(response), agentSessionStore: mockSessionStore.Object);

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "",
            ContextId = "ctx-1",
            Message = new Message
            {
                MessageId = "test-id",
                Role = Role.User,
                Parts = [new Part { Text = "Hello" }]
            }
        });

        // Assert - verify the custom session store was called
        mockSessionStore.Verify(
            x => x.GetSessionAsync(
                It.IsAny<AIAgent>(),
                It.Is<string>(s => s == "ctx-1"),
                It.IsAny<CancellationToken>()),
            Times.Once);
        mockSessionStore.Verify(
            x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.Is<string>(s => s == "ctx-1"),
                It.IsAny<AgentSession>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verifies that when no session store is provided, the default InMemoryAgentSessionStore
    /// persists sessions across multiple calls with the same context ID.
    /// </summary>
    [Fact]
    public async Task Handler_WithNullSessionStore_SessionIsPersistedAcrossCallsAsync()
    {
        // Arrange - track how many times CreateSessionCoreAsync is called
        int createSessionCallCount = 0;
        var sessionInstance = new TestAgentSession();

        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .Callback(() => Interlocked.Increment(ref createSessionCallCount))
            .ReturnsAsync(() => new TestAgentSession());
        agentMock
            .Protected()
            .Setup<ValueTask<JsonElement>>("SerializeSessionCoreAsync",
                ItExpr.IsAny<AgentSession>(),
                ItExpr.IsAny<JsonSerializerOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(JsonDocument.Parse("{}").RootElement);
        agentMock
            .Protected()
            .Setup<ValueTask<AgentSession>>("DeserializeSessionCoreAsync",
                ItExpr.IsAny<JsonElement>(),
                ItExpr.IsAny<JsonSerializerOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(sessionInstance);
        agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new AgentResponse([new ChatMessage(ChatRole.Assistant, "Reply")]));

        A2AAgentHandler handler = CreateHandler(agentMock, agentSessionStore: null);

        var context = new RequestContext
        {
            StreamingResponse = false,
            TaskId = "",
            ContextId = "ctx-persistent",
            Message = new Message
            {
                MessageId = "test-id",
                Role = Role.User,
                Parts = [new Part { Text = "Hello" }]
            }
        };

        // Act - call twice with the same context ID
        await InvokeExecuteAsync(handler, context);
        await InvokeExecuteAsync(handler, context);

        // Assert - CreateSessionCoreAsync should be called once (first call creates, second retrieves from store)
        Assert.Equal(1, createSessionCallCount);
    }

    /// <summary>
    /// Verifies that when the AllowBackgroundWhen delegate throws, the exception propagates
    /// and the agent is not invoked.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_DynamicMode_WhenCallbackThrows_PropagatesExceptionAsync()
    {
        // Arrange
        bool agentInvoked = false;
        A2AAgentHandler handler = CreateHandler(
            CreateAgentMock(_ => agentInvoked = true),
            runMode: AgentRunMode.AllowBackgroundWhen((_, _) =>
                throw new InvalidOperationException("Callback failed")));

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            InvokeExecuteAsync(handler, new RequestContext
            {
                TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
            }));

        Assert.False(agentInvoked);
    }

    /// <summary>
    /// Verifies that the CancellationToken is propagated to the AllowBackgroundWhen delegate.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_DynamicMode_CancellationTokenIsPropagatedToCallbackAsync()
    {
        // Arrange
        CancellationToken capturedToken = default;
        using var cts = new CancellationTokenSource();
        A2AAgentHandler handler = CreateHandler(
            CreateAgentMock(_ => { }),
            runMode: AgentRunMode.AllowBackgroundWhen((_, ct) =>
            {
                capturedToken = ct;
                return ValueTask.FromResult(false);
            }));

        // Act
        var eventQueue = new AgentEventQueue();
        await handler.ExecuteAsync(
            new RequestContext
            {
                TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
            },
            eventQueue,
            cts.Token);
        eventQueue.Complete(null);

        // Assert
        Assert.Equal(cts.Token, capturedToken);
    }

    /// <summary>
    /// Verifies that the agent run mode is applied on the continuation/task-update path,
    /// not just the new message path.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_OnContinuation_RunModeIsAppliedAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        A2AAgentHandler handler = CreateHandler(
            CreateAgentMock(options => capturedOptions = options),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "task-1",
            ContextId = "ctx-1",
            Message = new Message { MessageId = "empty", Role = Role.User, Parts = [] },

            Task = new AgentTask { Id = "task-1", ContextId = "ctx-1", History = [new Message { Role = Role.User, Parts = [new Part { Text = "Hello" }] }] }
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.True(capturedOptions.AllowBackgroundResponses);
    }

    private static A2AAgentHandler CreateHandler(
        Mock<AIAgent> agentMock,
        AgentRunMode? runMode = null,
        AgentSessionStore? agentSessionStore = null)
    {
        runMode ??= AgentRunMode.DisallowBackground;

        var hostAgent = new AIHostAgent(
            innerAgent: agentMock.Object,
            sessionStore: agentSessionStore ?? new InMemoryAgentSessionStore());

        return new A2AAgentHandler(hostAgent, runMode);
    }

    private static Mock<AIAgent> CreateAgentMock(Action<AgentRunOptions?> optionsCallback)
    {
        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new TestAgentSession());
        agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>(
                (_, _, options, _) => optionsCallback(options))
            .ReturnsAsync(new AgentResponse([new ChatMessage(ChatRole.Assistant, "Test response")]));

        return agentMock;
    }

    private static Mock<AIAgent> CreateAgentMockWithResponse(AgentResponse response)
    {
        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new TestAgentSession());
        agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(response);

        return agentMock;
    }

    private static Mock<AIAgent> CreateAgentMockWithCallCount(
        ref int callCount,
        Func<int, AgentResponse> responseFactory)
    {
        StrongBox<int> callCountBox = new(callCount);

        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new TestAgentSession());
        agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(() =>
            {
                int currentCall = Interlocked.Increment(ref callCountBox.Value);
                return responseFactory(currentCall);
            });

        return agentMock;
    }

    private static async Task InvokeExecuteAsync(A2AAgentHandler handler, RequestContext context)
    {
        var eventQueue = new AgentEventQueue();
        await handler.ExecuteAsync(context, eventQueue, CancellationToken.None);
        eventQueue.Complete(null);
    }

    private static async Task<EventCollector> CollectEventsAsync(A2AAgentHandler handler, RequestContext context)
    {
        var events = new EventCollector();
        var eventQueue = new AgentEventQueue();
        var readerTask = ReadEventsAsync(eventQueue, events);

        await handler.ExecuteAsync(context, eventQueue, CancellationToken.None);
        eventQueue.Complete(null);
        await readerTask;

        return events;
    }

    private static async Task ReadEventsAsync(AgentEventQueue eventQueue, EventCollector collector)
    {
        await foreach (var response in eventQueue)
        {
            switch (response.PayloadCase)
            {
                case StreamResponseCase.Message:
                    collector.Messages.Add(response.Message!);
                    break;
                case StreamResponseCase.Task:
                    collector.Tasks.Add(response.Task!);
                    break;
                case StreamResponseCase.StatusUpdate:
                    collector.StatusUpdates.Add(response.StatusUpdate!);
                    break;
                case StreamResponseCase.ArtifactUpdate:
                    collector.ArtifactUpdates.Add(response.ArtifactUpdate!);
                    break;
            }
        }
    }

#pragma warning disable MEAI001
    private static ResponseContinuationToken CreateTestContinuationToken()
    {
        return ResponseContinuationToken.FromBytes(new byte[] { 0x01, 0x02, 0x03 });
    }
#pragma warning restore MEAI001

    private sealed class EventCollector
    {
        public List<Message> Messages { get; } = [];
        public List<AgentTask> Tasks { get; } = [];
        public List<TaskStatusUpdateEvent> StatusUpdates { get; } = [];
        public List<TaskArtifactUpdateEvent> ArtifactUpdates { get; } = [];
    }

    private sealed class TestAgentSession : AgentSession;
}
