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
    /// The <see cref="AgentRunOptions.AdditionalProperties"/> key the handler forwards the A2A configuration under.
    /// </summary>
    private const string ConfigurationPropertyKey = "a2a.configuration";

    /// <summary>
    /// Verifies that when there is no request data to forward, null options are passed to RunStreamingAsync.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenMetadataIsNull_PassesNullOptionsToRunStreamingAsync()
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
        Assert.Null(capturedOptions);
    }

    /// <summary>
    /// Verifies that when metadata is non-empty, the options passed to RunStreamingAsync have
    /// AllowBackgroundResponses unset and AdditionalProperties populated with the converted metadata values.
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
        Assert.Null(capturedOptions.AllowBackgroundResponses);
        Assert.NotNull(capturedOptions.AdditionalProperties);
        Assert.Equal(2, capturedOptions.AdditionalProperties.Count);
        Assert.Equal("value1", capturedOptions.AdditionalProperties["key1"]?.ToString());
    }

    /// <summary>
    /// Verifies that when the caller supplies a <c>MessageSendParams.configuration</c>, it is forwarded to the
    /// agent through <see cref="AgentRunOptions.AdditionalProperties"/>.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenConfigurationIsProvided_ForwardsConfigurationToRunAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        A2AAgentHandler handler = CreateHandler(CreateAgentMock(options => capturedOptions = options));
        SendMessageConfiguration configuration = new()
        {
            AcceptedOutputModes = ["text/plain", "image/png"],
            HistoryLength = 10
        };

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false,
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] },
            Configuration = configuration
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.NotNull(capturedOptions.AdditionalProperties);
        Assert.Same(configuration, Assert.Single(capturedOptions.AdditionalProperties).Value);
        Assert.Equal(ConfigurationPropertyKey, Assert.Single(capturedOptions.AdditionalProperties).Key);
    }

    /// <summary>
    /// Verifies that the caller supplied configuration and metadata are both forwarded to the agent.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenConfigurationAndMetadataAreProvided_ForwardsBothToRunAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        A2AAgentHandler handler = CreateHandler(CreateAgentMock(options => capturedOptions = options));
        SendMessageConfiguration configuration = new() { HistoryLength = 5 };

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false,
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] },
            Metadata = new Dictionary<string, JsonElement>
            {
                ["key1"] = JsonSerializer.SerializeToElement("value1")
            },
            Configuration = configuration
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.NotNull(capturedOptions.AdditionalProperties);
        Assert.Equal(2, capturedOptions.AdditionalProperties.Count);
        Assert.Equal("value1", capturedOptions.AdditionalProperties["key1"]?.ToString());
        Assert.Same(configuration, capturedOptions.AdditionalProperties[ConfigurationPropertyKey]);
    }

    /// <summary>
    /// Verifies that the caller supplied configuration does not set AllowBackgroundResponses for a streaming run.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenConfigurationRequestsImmediateReturn_DoesNotSetAllowBackgroundResponsesAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        A2AAgentHandler handler = CreateHandler(
            CreateAgentMock(options => capturedOptions = options),
            runMode: AgentRunMode.DisallowBackground);

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false,
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] },
            Configuration = new SendMessageConfiguration { ReturnImmediately = true }
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.Null(capturedOptions.AllowBackgroundResponses);
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
    /// Verifies that a custom run-mode delegate returning false produces a message.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_DynamicMode_WithFalseCallback_ReturnsMessageAsync()
    {
        // Arrange
        A2AAgentHandler handler = CreateHandler(
            CreateAgentMock(_ => { }),
            runMode: AgentRunMode.AllowBackgroundWhen((_, _) => ValueTask.FromResult(false)));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Single(events.Messages);
        Assert.Empty(events.Tasks);
    }

    /// <summary>
    /// Verifies that a custom run-mode delegate returning true produces a task.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_DynamicMode_WithTrueCallback_ReturnsTaskAsync()
    {
        // Arrange
        A2AAgentHandler handler = CreateHandler(
            CreateAgentMock(_ => { }),
            runMode: AgentRunMode.AllowBackgroundWhen((_, _) => ValueTask.FromResult(true)));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            TaskId = "", ContextId = "ctx", StreamingResponse = false, Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Empty(events.Messages);
        Assert.Single(events.Tasks);
    }

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

    /// <summary>
    /// Verifies that an immediate request emits the initial task and streams subsequent updates when background responses are allowed.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenBackgroundResponsesAllowedAndReturnImmediatelyTrue_StreamsTaskUpdatesAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 1") { ResponseId = "r1", MessageId = "m1" },
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 2")
            {
                ResponseId = "r1",
                MessageId = "m1",
                ContinuationToken = CreateTestContinuationToken()
            },
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "task-1",
            ContextId = "ctx-1",
            Configuration = new SendMessageConfiguration { ReturnImmediately = true },
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Empty(events.Messages);
        Assert.Equal(TaskState.Submitted, Assert.Single(events.Tasks).Status.State);
        Assert.Collection(
            events.StatusUpdates,
            update => Assert.Equal(TaskState.Working, update.Status.State),
            update => Assert.Equal(TaskState.Completed, update.Status.State));
        Assert.Collection(
            events.ArtifactUpdates,
            update =>
            {
                Assert.Equal("chunk 1", Assert.Single(update.Artifact.Parts!).Text);
                Assert.False(update.Append);
                Assert.False(update.LastChunk);
            },
            update =>
            {
                Assert.Equal("chunk 2", Assert.Single(update.Artifact.Parts!).Text);
                Assert.True(update.Append);
                Assert.True(update.LastChunk);
            });
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

#pragma warning disable MEAI001

    /// <summary>
    /// Verifies that in streaming mode, updates from RunStreamingAsync are aggregated into one message event.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_EnqueuesSingleAggregatedMessageAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, (string?)null)
            {
                ResponseId = "r1",
                MessageId = "m1",
                ContinuationToken = CreateTestContinuationToken()
            },
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 1") { ResponseId = "r1", MessageId = "m1" },
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 2") { ResponseId = "r1", MessageId = "m1" },
            new AgentResponseUpdate(ChatRole.Assistant, (string?)null)
            {
                ResponseId = "r1",
                MessageId = "m1",
                ContinuationToken = CreateTestContinuationToken()
            }
        ];
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMock(updates));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Part part = Assert.Single(message.Parts!);
        Assert.Equal("chunk 1chunk 2", part.Text);
    }

    /// <summary>
    /// Verifies that allowing background responses emits a task lifecycle in streaming mode.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WhenBackgroundResponsesAllowed_StreamsTaskUpdatesAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 1")
            {
                ResponseId = "r1",
                MessageId = "m1"
            },
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 2")
            {
                ResponseId = "r1",
                MessageId = "m1",
                ContinuationToken = CreateTestContinuationToken()
            },
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 3")
            {
                ResponseId = "r1",
                MessageId = "m2"
            },
            new AgentResponseUpdate(ChatRole.Assistant, (string?)null)
            {
                ResponseId = "r1",
                MessageId = "m2"
            }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "task-1",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Empty(events.Messages);
        AgentTask task = Assert.Single(events.Tasks);
        Assert.Equal(TaskState.Submitted, task.Status.State);
        Assert.Collection(
            events.StatusUpdates,
            update =>
            {
                Assert.Equal(TaskState.Working, update.Status.State);
                Assert.Null(update.Status.Message);
            },
            update => Assert.Equal(TaskState.Completed, update.Status.State));
        Assert.Collection(
            events.ArtifactUpdates,
            update =>
            {
                Assert.Equal("chunk 1", Assert.Single(update.Artifact.Parts!).Text);
                Assert.Equal("m1", update.Artifact.ArtifactId);
                Assert.False(update.Append);
                Assert.False(update.LastChunk);
            },
            update =>
            {
                Assert.Equal("chunk 2", Assert.Single(update.Artifact.Parts!).Text);
                Assert.Equal("m1", update.Artifact.ArtifactId);
                Assert.True(update.Append);
                Assert.True(update.LastChunk);
            },
            update =>
            {
                Assert.Equal("chunk 3", Assert.Single(update.Artifact.Parts!).Text);
                Assert.Equal("m2", update.Artifact.ArtifactId);
                Assert.False(update.Append);
                Assert.True(update.LastChunk);
            });
    }

    /// <summary>
    /// Verifies that a non-immediate request aggregates all updates into a completed task.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenBackgroundResponsesAllowedAndReturnImmediatelyFalse_ReturnsCompletedTaskAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 1") { ResponseId = "r1", MessageId = "m1" },
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 2") { ResponseId = "r1", MessageId = "m1" }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "task-1",
            ContextId = "ctx",
            Configuration = new SendMessageConfiguration { ReturnImmediately = false },
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Empty(events.Messages);
        Assert.Equal(TaskState.Submitted, Assert.Single(events.Tasks).Status.State);
        Assert.Equal(TaskState.Completed, Assert.Single(events.StatusUpdates).Status.State);
        Assert.Equal("chunk 1chunk 2", Assert.Single(Assert.Single(events.ArtifactUpdates).Artifact.Parts!).Text);
    }

    /// <summary>
    /// Verifies that an aggregated task artifact preserves response metadata.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenAggregatingTaskUpdates_PreservesArtifactMetadataAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "result")
            {
                ResponseId = "r1",
                AdditionalProperties = new AdditionalPropertiesDictionary
                {
                    ["responseKey"] = "responseValue"
                }
            }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "task-1",
            ContextId = "ctx",
            Configuration = new SendMessageConfiguration { ReturnImmediately = false },
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Artifact artifact = Assert.Single(events.ArtifactUpdates).Artifact;
        Assert.Equal("responseValue", artifact.Metadata!["responseKey"].GetString());
    }

    /// <summary>
    /// Verifies that cancellation while emitting an aggregated task transitions the submitted task to Canceled.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenAggregatedTaskEmissionIsCanceled_CancelsTaskAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "result")
            {
                ResponseId = "r1",
                AdditionalProperties = new AdditionalPropertiesDictionary
                {
                    ["responseKey"] = new CallbackMetadataValue(cts.Cancel)
                }
            }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.AllowBackgroundIfSupported);
        var events = new EventCollector();
        var eventQueue = new AgentEventQueue();
        var readerTask = ReadEventsAsync(eventQueue, events);

        // Act
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            handler.ExecuteAsync(
                new RequestContext
                {
                    StreamingResponse = false,
                    TaskId = "task-1",
                    ContextId = "ctx",
                    Configuration = new SendMessageConfiguration { ReturnImmediately = false },
                    Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
                },
                eventQueue,
                cts.Token));
        eventQueue.Complete(null);
        await readerTask;

        // Assert
        Assert.Equal(TaskState.Submitted, Assert.Single(events.Tasks).Status.State);
        Assert.Equal(TaskState.Canceled, Assert.Single(events.StatusUpdates).Status.State);
        Assert.Empty(events.ArtifactUpdates);
    }

    /// <summary>
    /// Verifies that a failure while emitting an aggregated task transitions the submitted task to Failed.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenAggregatedTaskEmissionFails_FailsTaskAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "result")
            {
                ResponseId = "r1",
                AdditionalProperties = new AdditionalPropertiesDictionary
                {
                    ["responseKey"] = new CallbackMetadataValue(
                        () => throw new InvalidOperationException("Metadata serialization failed"))
                }
            }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsForThrowingExecuteAsync<InvalidOperationException>(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "task-1",
            ContextId = "ctx",
            Configuration = new SendMessageConfiguration { ReturnImmediately = false },
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Equal(TaskState.Submitted, Assert.Single(events.Tasks).Status.State);
        TaskStatusUpdateEvent statusUpdate = Assert.Single(events.StatusUpdates);
        Assert.Equal(TaskState.Failed, statusUpdate.Status.State);
        Assert.Equal(
            "The agent encountered an unexpected error and could not complete the request.",
            Assert.Single(statusUpdate.Status.Message!.Parts!).Text);
        Assert.Empty(events.ArtifactUpdates);
    }

    /// <summary>
    /// Verifies that an immediate request returns one aggregated message when background responses are disabled.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenBackgroundResponsesDisallowedAndReturnImmediatelyTrue_ReturnsMessageAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 1") { ResponseId = "r1", MessageId = "m1" },
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 2") { ResponseId = "r1", MessageId = "m1" }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.DisallowBackground);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "task-1",
            ContextId = "ctx",
            Configuration = new SendMessageConfiguration { ReturnImmediately = true },
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Empty(events.Tasks);
        Assert.Empty(events.StatusUpdates);
        Assert.Empty(events.ArtifactUpdates);
        Assert.Equal("chunk 1chunk 2", Assert.Single(Assert.Single(events.Messages).Parts!).Text);
    }

    /// <summary>
    /// Verifies that a non-immediate request aggregates all updates into one message when background responses are disabled.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_WhenBackgroundResponsesDisallowedAndReturnImmediatelyFalse_ReturnsMessageAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 1") { ResponseId = "r1", MessageId = "m1" },
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 2") { ResponseId = "r1", MessageId = "m1" }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.DisallowBackground);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = false,
            TaskId = "task-1",
            ContextId = "ctx",
            Configuration = new SendMessageConfiguration { ReturnImmediately = false },
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Empty(events.Tasks);
        Assert.Empty(events.StatusUpdates);
        Assert.Empty(events.ArtifactUpdates);
        Assert.Equal("chunk 1chunk 2", Assert.Single(Assert.Single(events.Messages).Parts!).Text);
    }

    /// <summary>
    /// Verifies that updates without message IDs continue the current artifact.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WithoutMessageId_ContinuesCurrentArtifactAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "m1 chunk 1") { ResponseId = "r1", MessageId = "m1" },
            new AgentResponseUpdate(ChatRole.Assistant, "m1 chunk 2") { ResponseId = "r1" },
            new AgentResponseUpdate(ChatRole.Assistant, "m2 chunk 1") { ResponseId = "r1", MessageId = "m2" },
            new AgentResponseUpdate(ChatRole.Assistant, "m2 chunk 2") { ResponseId = "r1" }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "task-1",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Collection(
            events.ArtifactUpdates,
            update => AssertArtifactUpdate(update, "m1 chunk 1", "m1", append: false, lastChunk: false),
            update => AssertArtifactUpdate(update, "m1 chunk 2", "m1", append: true, lastChunk: true),
            update => AssertArtifactUpdate(update, "m2 chunk 1", "m2", append: false, lastChunk: false),
            update => AssertArtifactUpdate(update, "m2 chunk 2", "m2", append: true, lastChunk: true));

        static void AssertArtifactUpdate(TaskArtifactUpdateEvent update, string text, string artifactId, bool append, bool lastChunk)
        {
            Assert.Equal(text, Assert.Single(update.Artifact.Parts!).Text);
            Assert.Equal(artifactId, update.Artifact.ArtifactId);
            Assert.Equal(append, update.Append);
            Assert.Equal(lastChunk, update.LastChunk);
        }
    }

    /// <summary>
    /// Verifies that updates without message IDs are streamed as one fallback artifact.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WithoutMessageIds_StreamsSingleArtifactAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 1") { ResponseId = "r1" },
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 2") { ResponseId = "r1" }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "task-1",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Collection(
            events.ArtifactUpdates,
            update =>
            {
                Assert.Equal("chunk 1", Assert.Single(update.Artifact.Parts!).Text);
                Assert.False(update.Append);
                Assert.False(update.LastChunk);
            },
            update =>
            {
                Assert.Equal("chunk 2", Assert.Single(update.Artifact.Parts!).Text);
                Assert.Equal(events.ArtifactUpdates[0].Artifact.ArtifactId, update.Artifact.ArtifactId);
                Assert.True(update.Append);
                Assert.True(update.LastChunk);
            });
    }

    /// <summary>
    /// Verifies that empty message IDs are treated as missing and continue the current artifact.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WithEmptyMessageIds_StreamsSingleArtifactAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 1") { ResponseId = "r1", MessageId = "" },
            new AgentResponseUpdate(ChatRole.Assistant, "chunk 2") { ResponseId = "r1", MessageId = "" }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "task-1",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Collection(
            events.ArtifactUpdates,
            update =>
            {
                Assert.Equal("chunk 1", Assert.Single(update.Artifact.Parts!).Text);
                Assert.NotEmpty(update.Artifact.ArtifactId);
                Assert.False(update.Append);
                Assert.False(update.LastChunk);
            },
            update =>
            {
                Assert.Equal("chunk 2", Assert.Single(update.Artifact.Parts!).Text);
                Assert.Equal(events.ArtifactUpdates[0].Artifact.ArtifactId, update.Artifact.ArtifactId);
                Assert.True(update.Append);
                Assert.True(update.LastChunk);
            });
    }

    /// <summary>
    /// Verifies that cancellation during a streaming task flushes buffered content and emits the Canceled terminal state.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WhenCancellationRequested_CancelsTaskAsync()
    {
        // Arrange
        using var cts = new CancellationTokenSource();
        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock.Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new TestAgentSession());
        agentMock.Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(() => ToCancelingAsyncEnumerableAsync(cts));
        A2AAgentHandler handler = CreateHandler(agentMock, runMode: AgentRunMode.AllowBackgroundIfSupported);
        var events = new EventCollector();
        var eventQueue = new AgentEventQueue();
        var readerTask = ReadEventsAsync(eventQueue, events);

        // Act
        await Assert.ThrowsAsync<OperationCanceledException>(() =>
            handler.ExecuteAsync(
                new RequestContext
                {
                    StreamingResponse = true,
                    TaskId = "task-1",
                    ContextId = "ctx",
                    Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
                },
                eventQueue,
                cts.Token));
        eventQueue.Complete(null);
        await readerTask;

        // Assert
        Assert.Equal(TaskState.Submitted, Assert.Single(events.Tasks).Status.State);
        Assert.Collection(
            events.StatusUpdates,
            update => Assert.Equal(TaskState.Working, update.Status.State),
            update => Assert.Equal(TaskState.Canceled, update.Status.State));
        TaskArtifactUpdateEvent artifactUpdate = Assert.Single(events.ArtifactUpdates);
        Assert.Equal("chunk 1", Assert.Single(artifactUpdate.Artifact.Parts!).Text);
        Assert.False(artifactUpdate.Append);
        Assert.True(artifactUpdate.LastChunk);
    }

    /// <summary>
    /// Verifies that a failure during a streaming task flushes buffered content and emits the Failed terminal state.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WhenAgentThrows_FailsTaskAsync()
    {
        // Arrange
        A2AAgentHandler handler = CreateHandler(
            CreateThrowingStreamingAgentMock(
                [new AgentResponseUpdate(ChatRole.Assistant, "chunk 1") { ResponseId = "r1", MessageId = "m1" }],
                new InvalidOperationException("Stream failed")),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsForThrowingExecuteAsync<InvalidOperationException>(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "task-1",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Equal(TaskState.Submitted, Assert.Single(events.Tasks).Status.State);
        Assert.Collection(
            events.StatusUpdates,
            update => Assert.Equal(TaskState.Working, update.Status.State),
            update =>
            {
                Assert.Equal(TaskState.Failed, update.Status.State);

                // The status message must not leak exception details.
                string text = Assert.Single(update.Status.Message!.Parts!).Text!;
                Assert.DoesNotContain("Stream failed", text, StringComparison.Ordinal);
                Assert.DoesNotContain(nameof(InvalidOperationException), text, StringComparison.Ordinal);
                Assert.Equal("The agent encountered an unexpected error and could not complete the request.", text);
            });
        TaskArtifactUpdateEvent artifactUpdate = Assert.Single(events.ArtifactUpdates);
        Assert.Equal("chunk 1", Assert.Single(artifactUpdate.Artifact.Parts!).Text);
        Assert.False(artifactUpdate.Append);
        Assert.True(artifactUpdate.LastChunk);
    }

    /// <summary>
    /// Verifies that changing the message ID finalizes the previous artifact before the stream completes.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WhenMessageIdChanges_FinalizesPreviousArtifactImmediatelyAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "m1 chunk") { ResponseId = "r1", MessageId = "m1" },
            new AgentResponseUpdate(ChatRole.Assistant, "m2 chunk") { ResponseId = "r1", MessageId = "m2" }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateThrowingStreamingAgentMock(updates, new InvalidOperationException("Stream failed")),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsForThrowingExecuteAsync<InvalidOperationException>(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "task-1",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert - m1 was finalized at the m2 boundary, before m2 was flushed after the later stream failure.
        Assert.Collection(
            events.ArtifactUpdates,
            update =>
            {
                Assert.Equal("m1", update.Artifact.ArtifactId);
                Assert.Equal("m1 chunk", Assert.Single(update.Artifact.Parts!).Text);
                Assert.False(update.Append);
                Assert.True(update.LastChunk);
            },
            update =>
            {
                Assert.Equal("m2", update.Artifact.ArtifactId);
                Assert.Equal("m2 chunk", Assert.Single(update.Artifact.Parts!).Text);
                Assert.False(update.Append);
                Assert.True(update.LastChunk);
            });
    }

    /// <summary>
    /// Verifies that a message ID reused after another message produces a distinct artifact.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WhenMessageIdReappears_UsesDistinctArtifactIdAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "first m1") { ResponseId = "r1", MessageId = "m1" },
            new AgentResponseUpdate(ChatRole.Assistant, "m2") { ResponseId = "r1", MessageId = "m2" },
            new AgentResponseUpdate(ChatRole.Assistant, "second m1 chunk 1") { ResponseId = "r1", MessageId = "m1" },
            new AgentResponseUpdate(ChatRole.Assistant, "second m1 chunk 2") { ResponseId = "r1", MessageId = "m1" }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "task-1",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Collection(
            events.ArtifactUpdates,
            update =>
            {
                Assert.Equal("m1", update.Artifact.ArtifactId);
                Assert.Equal("first m1", Assert.Single(update.Artifact.Parts!).Text);
                Assert.False(update.Append);
                Assert.True(update.LastChunk);
            },
            update =>
            {
                Assert.Equal("m2", update.Artifact.ArtifactId);
                Assert.Equal("m2", Assert.Single(update.Artifact.Parts!).Text);
                Assert.False(update.Append);
                Assert.True(update.LastChunk);
            },
            update =>
            {
                Assert.NotEqual("m1", update.Artifact.ArtifactId);
                Assert.NotEqual("m2", update.Artifact.ArtifactId);
                Assert.Equal("second m1 chunk 1", Assert.Single(update.Artifact.Parts!).Text);
                Assert.False(update.Append);
                Assert.False(update.LastChunk);
            },
            update =>
            {
                Assert.Equal(events.ArtifactUpdates[2].Artifact.ArtifactId, update.Artifact.ArtifactId);
                Assert.Equal("second m1 chunk 2", Assert.Single(update.Artifact.Parts!).Text);
                Assert.True(update.Append);
                Assert.True(update.LastChunk);
            });
    }

    /// <summary>
    /// Verifies that an agent-initiated cancellation fails the task when the caller did not request cancellation.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WhenAgentThrowsOperationCanceledWithoutCancellation_FailsTaskAsync()
    {
        // Arrange
        A2AAgentHandler handler = CreateHandler(
            CreateThrowingStreamingAgentMock([], new OperationCanceledException("Agent gave up")),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsForThrowingExecuteAsync<OperationCanceledException>(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "task-1",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Equal(TaskState.Failed, events.StatusUpdates[^1].Status.State);
    }

    /// <summary>
    /// Verifies that a streaming task without any updates still reaches a terminal state.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WithNoUpdates_CompletesTaskAsync()
    {
        // Arrange
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock([]),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "task-1",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Empty(events.Messages);
        Assert.Empty(events.ArtifactUpdates);
        Assert.Equal(TaskState.Submitted, Assert.Single(events.Tasks).Status.State);
        Assert.Collection(
            events.StatusUpdates,
            update => Assert.Equal(TaskState.Working, update.Status.State),
            update => Assert.Equal(TaskState.Completed, update.Status.State));
    }

    /// <summary>
    /// Verifies that updates carrying no content produce no artifacts but still complete the task.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WithOnlyContentlessUpdates_CompletesTaskWithoutArtifactsAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, (string?)null) { ResponseId = "r1", MessageId = "m1" },
            new AgentResponseUpdate(ChatRole.Assistant, (string?)null) { ResponseId = "r1", MessageId = "m1" }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "task-1",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Empty(events.ArtifactUpdates);
        Assert.Equal(TaskState.Completed, events.StatusUpdates[^1].Status.State);
    }

    /// <summary>
    /// Verifies that a contentless update with a new message ID finalizes the previous artifact.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WhenContentlessUpdateChangesMessageId_FinalizesPreviousArtifactAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "m1 chunk") { ResponseId = "r1", MessageId = "m1" },
            new AgentResponseUpdate(ChatRole.Assistant, (string?)null) { ResponseId = "r1", MessageId = "m2" },
            new AgentResponseUpdate(ChatRole.Assistant, "m2 chunk") { ResponseId = "r1", MessageId = "m2" }
        ];
        A2AAgentHandler handler = CreateHandler(
            CreateStreamingAgentMock(updates),
            runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "task-1",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Collection(
            events.ArtifactUpdates,
            update =>
            {
                Assert.Equal("m1", update.Artifact.ArtifactId);
                Assert.Equal("m1 chunk", Assert.Single(update.Artifact.Parts!).Text);
            },
            update =>
            {
                Assert.Equal("m2", update.Artifact.ArtifactId);
                Assert.Equal("m2 chunk", Assert.Single(update.Artifact.Parts!).Text);
            });
        Assert.All(events.ArtifactUpdates, update =>
        {
            Assert.False(update.Append);
            Assert.True(update.LastChunk);
        });
    }

#pragma warning restore MEAI001

    /// <summary>
    /// Verifies that in streaming mode, when metadata is present, options with AdditionalProperties
    /// are passed to RunStreamingAsync.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WithMetadata_PassesOptionsWithAdditionalPropertiesAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMockWithOptionsCapture(
            options => capturedOptions = options));

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] },
            Metadata = new Dictionary<string, JsonElement>
            {
                ["key1"] = JsonSerializer.SerializeToElement("value1")
            }
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.NotNull(capturedOptions.AdditionalProperties);
        Assert.Equal("value1", capturedOptions.AdditionalProperties["key1"]?.ToString());
    }

    /// <summary>
    /// Verifies that streaming mode passes null options when metadata is null.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WithNullMetadata_PassesNullOptionsAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        bool optionsCaptured = false;
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMockWithOptionsCapture(
            options => { capturedOptions = options; optionsCaptured = true; }));

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.True(optionsCaptured);
        Assert.Null(capturedOptions);
    }

    /// <summary>
    /// Verifies that in streaming mode, when only a configuration is present, options carrying the
    /// configuration are passed to RunStreamingAsync.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WithConfiguration_PassesOptionsWithConfigurationAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMockWithOptionsCapture(
            options => capturedOptions = options));
        SendMessageConfiguration configuration = new() { AcceptedOutputModes = ["text/plain"] };

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] },
            Configuration = configuration
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.Null(capturedOptions.AllowBackgroundResponses);
        Assert.NotNull(capturedOptions.AdditionalProperties);
        Assert.Same(configuration, capturedOptions.AdditionalProperties[ConfigurationPropertyKey]);
    }

    /// <summary>
    /// Verifies that in streaming mode, ReferenceTaskIds throws NotSupportedException.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WithReferenceTaskIds_ThrowsNotSupportedExceptionAsync()
    {
        // Arrange
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMock([]));

        // Act & Assert
        var eventQueue = new AgentEventQueue();
        await Assert.ThrowsAsync<NotSupportedException>(() =>
            handler.ExecuteAsync(
                new RequestContext
                {
                    StreamingResponse = true,
                    TaskId = "",
                    ContextId = "ctx",
                    Message = new Message
                    {
                        MessageId = "test-id",
                        Role = Role.User,
                        Parts = [new Part { Text = "Hello" }],
                        ReferenceTaskIds = ["other-task-id"]
                    }
                },
                eventQueue,
                CancellationToken.None));
    }

    /// <summary>
    /// Verifies that in streaming mode, when ContextId is null, a new one is generated.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WhenContextIdIsNull_GeneratesContextIdAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "Reply") { ResponseId = "r1" }
        ];
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMock(updates));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = null!,
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.NotNull(message.ContextId);
        Assert.NotEmpty(message.ContextId);
    }

    /// <summary>
    /// Verifies that in streaming mode, the provided ContextId is used in the response.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_UsesProvidedContextIdAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "Reply") { ResponseId = "r1" }
        ];
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMock(updates));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = "my-streaming-ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.Equal("my-streaming-ctx", message.ContextId);
    }

    /// <summary>
    /// Verifies that in streaming mode, when Message is null, the handler succeeds with empty messages.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WhenMessageIsNull_SucceedsWithEmptyMessagesAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "Reply") { ResponseId = "r1" }
        ];
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMock(updates));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = "ctx",
            Message = null!
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.Equal("ctx", message.ContextId);
    }

    /// <summary>
    /// Verifies that in streaming mode, the ResponseId from the update is used as the MessageId in the response.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_ResponseIdIsUsedAsMessageIdAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "chunk") { ResponseId = "resp-42" }
        ];
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMock(updates));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.Equal("resp-42", message.MessageId);
    }

    /// <summary>
    /// Verifies that in streaming mode, when ResponseId is null, a MessageId is still generated.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WhenResponseIdIsNull_GeneratesMessageIdAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "chunk") { ResponseId = null }
        ];
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMock(updates));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.NotNull(message.MessageId);
        Assert.NotEmpty(message.MessageId);
    }

    /// <summary>
    /// Verifies that in streaming mode, when the update has AdditionalProperties, the message has metadata.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WithResponseAdditionalProperties_ReturnsMessageWithMetadataAsync()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProps = new()
        {
            ["streamKey"] = "streamValue"
        };
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "chunk") { ResponseId = "r1", AdditionalProperties = additionalProps }
        ];
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMock(updates));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.NotNull(message.Metadata);
        Assert.True(message.Metadata.ContainsKey("streamKey"));
    }

    /// <summary>
    /// Verifies that in streaming mode, when the update has null AdditionalProperties, the message has null metadata.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WithNullAdditionalProperties_ReturnsMessageWithNullMetadataAsync()
    {
        // Arrange
        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "chunk") { ResponseId = "r1", AdditionalProperties = null }
        ];
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMock(updates));

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Message message = Assert.Single(events.Messages);
        Assert.Null(message.Metadata);
    }

    /// <summary>
    /// Verifies that in streaming mode, the session is saved after all updates are processed.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_SavesSessionAfterProcessingAsync()
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

        AgentResponseUpdate[] updates =
        [
            new AgentResponseUpdate(ChatRole.Assistant, "chunk") { ResponseId = "r1" }
        ];
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMock(updates), agentSessionStore: mockSessionStore.Object);

        // Act
        await InvokeExecuteAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = "ctx-stream",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert - verify session was saved
        mockSessionStore.Verify(
            x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.Is<string>(s => s == "ctx-stream"),
                It.IsAny<AgentSession>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verifies that in streaming mode, when RunStreamingAsync yields no updates,
    /// an empty message is enqueued and the session is still saved.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WhenNoUpdates_EnqueuesEmptyMessageAndSavesSessionAsync()
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

        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMock([]), agentSessionStore: mockSessionStore.Object);

        // Act
        var events = await CollectEventsAsync(handler, new RequestContext
        {
            StreamingResponse = true,
            TaskId = "",
            ContextId = "ctx",
            Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
        });

        // Assert
        Assert.Empty(Assert.Single(events.Messages).Parts!);
        mockSessionStore.Verify(
            x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.Is<string>(s => s == "ctx"),
                It.IsAny<AgentSession>(),
                It.IsAny<CancellationToken>()),
            Times.Once);
    }

    /// <summary>
    /// Verifies that the CancellationToken is propagated to RunStreamingAsync in the streaming path.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_CancellationTokenIsPropagatedToRunStreamingAsync()
    {
        // Arrange
        CancellationToken capturedToken = default;
        using var cts = new CancellationTokenSource();

        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new TestAgentSession());
        agentMock
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>(
                (_, _, _, ct) => capturedToken = ct)
            .Returns(() => ToAsyncEnumerableAsync([new AgentResponseUpdate(ChatRole.Assistant, "reply") { ResponseId = "r1" }]));

        A2AAgentHandler handler = CreateHandler(agentMock);

        // Act
        var eventQueue = new AgentEventQueue();
        await handler.ExecuteAsync(
            new RequestContext
            {
                TaskId = "",
                ContextId = "ctx",
                StreamingResponse = true,
                Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
            },
            eventQueue,
            cts.Token);
        eventQueue.Complete(null);

        // Assert
        Assert.Equal(cts.Token, capturedToken);
    }

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
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(() => ToAsyncEnumerableAsync(
                new AgentResponse([new ChatMessage(ChatRole.Assistant, "Reply")]).ToAgentResponseUpdates()));

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

    /// <summary>
    /// Verifies that in the non-streaming endpoint path, SaveSessionAsync is called with
    /// CancellationToken.None even when RunStreamingAsync throws an exception.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_NonStreaming_WhenRunStreamingAsyncThrows_SavesSessionWithUncancelledTokenAsync()
    {
        // Arrange
        var mockSessionStore = new Mock<AgentSessionStore>();
        mockSessionStore
            .Setup(x => x.GetSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new TestAgentSession());
        mockSessionStore
            .Setup(x => x.SaveSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<AgentSession>(), It.IsAny<CancellationToken>()))
            .Returns(ValueTask.CompletedTask);

        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock.Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new TestAgentSession());
        agentMock.Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(() => ToThrowingAsyncEnumerableAsync(new InvalidOperationException("Agent failed")));

        using var cts = new CancellationTokenSource();
        A2AAgentHandler handler = CreateHandler(agentMock, agentSessionStore: mockSessionStore.Object);

        // Act
        var eventQueue = new AgentEventQueue();
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            handler.ExecuteAsync(
                new RequestContext
                {
                    TaskId = "", ContextId = "ctx", StreamingResponse = false,
                    Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
                },
                eventQueue,
                cts.Token));

        // Assert - SaveSessionAsync was called with CancellationToken.None despite the exception
        mockSessionStore.Verify(
            x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.Is<string>(s => s == "ctx"),
                It.IsAny<AgentSession>(),
                It.Is<CancellationToken>(ct => ct == CancellationToken.None)),
            Times.Once);
    }

    /// <summary>
    /// Verifies that in the streaming path, SaveSessionAsync is called with
    /// CancellationToken.None even when RunStreamingAsync throws an exception.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_WhenRunStreamingAsyncThrows_SavesSessionWithUncancelledTokenAsync()
    {
        // Arrange
        var mockSessionStore = new Mock<AgentSessionStore>();
        mockSessionStore
            .Setup(x => x.GetSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new TestAgentSession());
        mockSessionStore
            .Setup(x => x.SaveSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<AgentSession>(), It.IsAny<CancellationToken>()))
            .Returns(ValueTask.CompletedTask);

        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock.Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new TestAgentSession());
        agentMock.Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(() => ToThrowingAsyncEnumerableAsync(new InvalidOperationException("Stream failed")));

        using var cts = new CancellationTokenSource();
        A2AAgentHandler handler = CreateHandler(agentMock, agentSessionStore: mockSessionStore.Object);

        // Act
        var eventQueue = new AgentEventQueue();
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            handler.ExecuteAsync(
                new RequestContext
                {
                    TaskId = "", ContextId = "ctx-stream", StreamingResponse = true,
                    Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
                },
                eventQueue,
                cts.Token));

        // Assert - SaveSessionAsync was called with CancellationToken.None despite the exception
        mockSessionStore.Verify(
            x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.Is<string>(s => s == "ctx-stream"),
                It.IsAny<AgentSession>(),
                It.Is<CancellationToken>(ct => ct == CancellationToken.None)),
            Times.Once);
    }

    /// <summary>
    /// Verifies that on the continuation path, SaveSessionAsync is called with
    /// CancellationToken.None even when RunAsync throws an exception.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_OnContinuation_WhenRunAsyncThrows_SavesSessionWithUncancelledTokenAsync()
    {
        // Arrange
        var mockSessionStore = new Mock<AgentSessionStore>();
        mockSessionStore
            .Setup(x => x.GetSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new TestAgentSession());
        mockSessionStore
            .Setup(x => x.SaveSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<AgentSession>(), It.IsAny<CancellationToken>()))
            .Returns(ValueTask.CompletedTask);

        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock.Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new TestAgentSession());
        agentMock.Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ThrowsAsync(new InvalidOperationException("Agent failed"));

        using var cts = new CancellationTokenSource();
        A2AAgentHandler handler = CreateHandler(agentMock, agentSessionStore: mockSessionStore.Object);

        // Act
        var eventQueue = new AgentEventQueue();
        var events = new EventCollector();
        var readerTask = ReadEventsAsync(eventQueue, events);
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            handler.ExecuteAsync(
                new RequestContext
                {
                    StreamingResponse = false,
                    TaskId = "task-1", ContextId = "ctx-cont",
                    Message = new Message { MessageId = "empty", Role = Role.User, Parts = [] },
                    Task = new AgentTask { Id = "task-1", ContextId = "ctx-cont", History = [new Message { Role = Role.User, Parts = [new Part { Text = "Hello" }] }] }
                },
                eventQueue,
                cts.Token));
        eventQueue.Complete(null);
        await readerTask;

        // Assert - SaveSessionAsync was called with CancellationToken.None despite the exception
        mockSessionStore.Verify(
            x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.Is<string>(s => s == "ctx-cont"),
                It.IsAny<AgentSession>(),
                It.Is<CancellationToken>(ct => ct == CancellationToken.None)),
            Times.Once);
    }

    /// <summary>
    /// Verifies that in the non-streaming path, SaveSessionAsync is called with
    /// CancellationToken.None rather than the caller's cancellation token.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_NonStreaming_SavesSessionWithUncancelledTokenAsync()
    {
        // Arrange
        var mockSessionStore = new Mock<AgentSessionStore>();
        mockSessionStore
            .Setup(x => x.GetSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new TestAgentSession());
        mockSessionStore
            .Setup(x => x.SaveSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<AgentSession>(), It.IsAny<CancellationToken>()))
            .Returns(ValueTask.CompletedTask);

        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Reply")]);
        A2AAgentHandler handler = CreateHandler(CreateAgentMockWithResponse(response), agentSessionStore: mockSessionStore.Object);

        using var cts = new CancellationTokenSource();

        // Act
        var eventQueue = new AgentEventQueue();
        await handler.ExecuteAsync(
            new RequestContext
            {
                TaskId = "", ContextId = "ctx", StreamingResponse = false,
                Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
            },
            eventQueue,
            cts.Token);
        eventQueue.Complete(null);

        // Assert - SaveSessionAsync was called with CancellationToken.None, not the caller's token
        mockSessionStore.Verify(
            x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.Is<string>(s => s == "ctx"),
                It.IsAny<AgentSession>(),
                It.Is<CancellationToken>(ct => ct == CancellationToken.None)),
            Times.Once);
    }

    /// <summary>
    /// Verifies that in the streaming path, SaveSessionAsync is called with
    /// CancellationToken.None rather than the caller's cancellation token.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_Streaming_SavesSessionWithUncancelledTokenAsync()
    {
        // Arrange
        var mockSessionStore = new Mock<AgentSessionStore>();
        mockSessionStore
            .Setup(x => x.GetSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new TestAgentSession());
        mockSessionStore
            .Setup(x => x.SaveSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<AgentSession>(), It.IsAny<CancellationToken>()))
            .Returns(ValueTask.CompletedTask);

        AgentResponseUpdate[] updates = [new AgentResponseUpdate(ChatRole.Assistant, "chunk") { ResponseId = "r1" }];
        A2AAgentHandler handler = CreateHandler(CreateStreamingAgentMock(updates), agentSessionStore: mockSessionStore.Object);

        using var cts = new CancellationTokenSource();

        // Act
        var eventQueue = new AgentEventQueue();
        await handler.ExecuteAsync(
            new RequestContext
            {
                TaskId = "", ContextId = "ctx-stream", StreamingResponse = true,
                Message = new Message { MessageId = "test-id", Role = Role.User, Parts = [new Part { Text = "Hello" }] }
            },
            eventQueue,
            cts.Token);
        eventQueue.Complete(null);

        // Assert - SaveSessionAsync was called with CancellationToken.None, not the caller's token
        mockSessionStore.Verify(
            x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.Is<string>(s => s == "ctx-stream"),
                It.IsAny<AgentSession>(),
                It.Is<CancellationToken>(ct => ct == CancellationToken.None)),
            Times.Once);
    }

    /// <summary>
    /// Verifies that on the continuation path, SaveSessionAsync is called with
    /// CancellationToken.None rather than the caller's cancellation token.
    /// </summary>
    [Fact]
    public async Task ExecuteAsync_OnContinuation_SavesSessionWithUncancelledTokenAsync()
    {
        // Arrange
        var mockSessionStore = new Mock<AgentSessionStore>();
        mockSessionStore
            .Setup(x => x.GetSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new TestAgentSession());
        mockSessionStore
            .Setup(x => x.SaveSessionAsync(It.IsAny<AIAgent>(), It.IsAny<string>(), It.IsAny<AgentSession>(), It.IsAny<CancellationToken>()))
            .Returns(ValueTask.CompletedTask);

        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Done!")]);
        A2AAgentHandler handler = CreateHandler(CreateAgentMockWithResponse(response), agentSessionStore: mockSessionStore.Object);

        using var cts = new CancellationTokenSource();

        // Act
        var eventQueue = new AgentEventQueue();
        var events = new EventCollector();
        var readerTask = ReadEventsAsync(eventQueue, events);
        await handler.ExecuteAsync(
            new RequestContext
            {
                StreamingResponse = false,
                TaskId = "task-1", ContextId = "ctx-cont",
                Message = new Message { MessageId = "empty", Role = Role.User, Parts = [] },
                Task = new AgentTask { Id = "task-1", ContextId = "ctx-cont", History = [new Message { Role = Role.User, Parts = [new Part { Text = "Hello" }] }] }
            },
            eventQueue,
            cts.Token);
        eventQueue.Complete(null);
        await readerTask;

        // Assert - SaveSessionAsync was called with CancellationToken.None, not the caller's token
        mockSessionStore.Verify(
            x => x.SaveSessionAsync(
                It.IsAny<AIAgent>(),
                It.Is<string>(s => s == "ctx-cont"),
                It.IsAny<AgentSession>(),
                It.Is<CancellationToken>(ct => ct == CancellationToken.None)),
            Times.Once);
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
        agentMock
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>(
                (_, _, options, _) => optionsCallback(options))
            .Returns(() => ToAsyncEnumerableAsync(
                new AgentResponse([new ChatMessage(ChatRole.Assistant, "Test response")]).ToAgentResponseUpdates()));

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
        agentMock
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(() => ToAsyncEnumerableAsync(response.ToAgentResponseUpdates()));

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

    private static Mock<AIAgent> CreateStreamingAgentMock(IEnumerable<AgentResponseUpdate> updates)
    {
        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new TestAgentSession());
        agentMock
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(() => ToAsyncEnumerableAsync(updates));

        return agentMock;
    }

    private static Mock<AIAgent> CreateThrowingStreamingAgentMock(IEnumerable<AgentResponseUpdate> updates, Exception exception)
    {
        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new TestAgentSession());
        agentMock
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Returns(() => ToThrowingAsyncEnumerableAsync(updates, exception));

        return agentMock;
    }

    private static Mock<AIAgent> CreateStreamingAgentMockWithOptionsCapture(
        Action<AgentRunOptions?> optionsCallback)
    {
        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock
            .Protected()
            .Setup<ValueTask<AgentSession>>("CreateSessionCoreAsync", ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(new TestAgentSession());
        agentMock
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentSession?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentSession?, AgentRunOptions?, CancellationToken>(
                (_, _, options, _) => optionsCallback(options))
            .Returns(() => ToAsyncEnumerableAsync([new AgentResponseUpdate(ChatRole.Assistant, "reply") { ResponseId = "r1" }]));

        return agentMock;
    }

    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(IEnumerable<T> items)
    {
        await Task.Yield();
        foreach (var item in items)
        {
            yield return item;
        }
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> ToThrowingAsyncEnumerableAsync(Exception exception)
    {
        await Task.Yield();
        throw exception;

#pragma warning disable CS0162 // Unreachable code detected - yield is required for async iterator
        yield break;
#pragma warning restore CS0162
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> ToThrowingAsyncEnumerableAsync(IEnumerable<AgentResponseUpdate> items, Exception exception)
    {
        await Task.Yield();
        foreach (var item in items)
        {
            yield return item;
        }

        throw exception;
    }

    private static async IAsyncEnumerable<AgentResponseUpdate> ToCancelingAsyncEnumerableAsync(CancellationTokenSource cts)
    {
        yield return new AgentResponseUpdate(ChatRole.Assistant, "chunk 1") { ResponseId = "r1", MessageId = "m1" };

        await Task.Yield();
        cts.Cancel();
        cts.Token.ThrowIfCancellationRequested();
    }

    private static async Task InvokeExecuteAsync(A2AAgentHandler handler, RequestContext context)
    {
        var eventQueue = new AgentEventQueue();
        await handler.ExecuteAsync(context, eventQueue, CancellationToken.None);
        eventQueue.Complete(null);
    }

    private static async Task<EventCollector> CollectEventsForThrowingExecuteAsync<TException>(A2AAgentHandler handler, RequestContext context)
        where TException : Exception
    {
        var events = new EventCollector();
        var eventQueue = new AgentEventQueue();
        var readerTask = ReadEventsAsync(eventQueue, events);

        await Assert.ThrowsAsync<TException>(() => handler.ExecuteAsync(context, eventQueue, CancellationToken.None));
        eventQueue.Complete(null);
        await readerTask;

        return events;
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

    private sealed class CallbackMetadataValue(Action callback)
    {
        public string Value
        {
            get
            {
                callback();
                return "value";
            }
        }
    }

    private sealed class TestAgentSession : AgentSession;
}
