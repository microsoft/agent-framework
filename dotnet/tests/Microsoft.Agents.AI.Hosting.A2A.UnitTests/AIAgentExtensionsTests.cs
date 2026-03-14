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
/// Unit tests for the <see cref="AIAgentExtensions"/> class.
/// </summary>
public sealed class AIAgentExtensionsTests
{
    /// <summary>
    /// Verifies that when messageSendParams.Metadata is null, the options passed to RunAsync have
    /// AllowBackgroundResponses enabled and no AdditionalProperties.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenMetadataIsNull_PassesOptionsWithNoAdditionalPropertiesToRunAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        ITaskManager taskManager = CreateAgentMock(options => capturedOptions = options).Object.MapA2A();

        // Act
        await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] },
            Metadata = null
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.False(capturedOptions.AllowBackgroundResponses);
        Assert.Null(capturedOptions.AdditionalProperties);
    }

    /// <summary>
    /// Verifies that when messageSendParams.Metadata has values, the options.AdditionalProperties contains the converted values.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenMetadataHasValues_PassesOptionsWithAdditionalPropertiesToRunAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        ITaskManager taskManager = CreateAgentMock(options => capturedOptions = options).Object.MapA2A();

        // Act
        await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] },
            Metadata = new Dictionary<string, JsonElement>
            {
                ["key1"] = JsonSerializer.SerializeToElement("value1"),
                ["key2"] = JsonSerializer.SerializeToElement(42)
            }
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.NotNull(capturedOptions.AdditionalProperties);
        Assert.Equal(2, capturedOptions.AdditionalProperties.Count);
        Assert.True(capturedOptions.AdditionalProperties.ContainsKey("key1"));
        Assert.True(capturedOptions.AdditionalProperties.ContainsKey("key2"));
    }

    /// <summary>
    /// Verifies that when messageSendParams.Metadata is an empty dictionary, the options passed to RunAsync have
    /// AllowBackgroundResponses enabled and no AdditionalProperties.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenMetadataIsEmptyDictionary_PassesOptionsWithNoAdditionalPropertiesToRunAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        ITaskManager taskManager = CreateAgentMock(options => capturedOptions = options).Object.MapA2A();

        // Act
        await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] },
            Metadata = []
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.False(capturedOptions.AllowBackgroundResponses);
        Assert.Null(capturedOptions.AdditionalProperties);
    }

    /// <summary>
    /// Verifies that when the agent response has AdditionalProperties, the returned AgentMessage.Metadata contains the converted values.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenResponseHasAdditionalProperties_ReturnsAgentMessageWithMetadataAsync()
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
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        AgentMessage agentMessage = Assert.IsType<AgentMessage>(a2aResponse);
        Assert.NotNull(agentMessage.Metadata);
        Assert.Equal(2, agentMessage.Metadata.Count);
        Assert.True(agentMessage.Metadata.ContainsKey("responseKey1"));
        Assert.True(agentMessage.Metadata.ContainsKey("responseKey2"));
        Assert.Equal("responseValue1", agentMessage.Metadata["responseKey1"].GetString());
        Assert.Equal(123, agentMessage.Metadata["responseKey2"].GetInt32());
    }

    /// <summary>
    /// Verifies that when the agent response has null AdditionalProperties, the returned AgentMessage.Metadata is null.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenResponseHasNullAdditionalProperties_ReturnsAgentMessageWithNullMetadataAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Test response")])
        {
            AdditionalProperties = null
        };
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        AgentMessage agentMessage = Assert.IsType<AgentMessage>(a2aResponse);
        Assert.Null(agentMessage.Metadata);
    }

    /// <summary>
    /// Verifies that when the agent response has empty AdditionalProperties, the returned AgentMessage.Metadata is null.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenResponseHasEmptyAdditionalProperties_ReturnsAgentMessageWithNullMetadataAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Test response")])
        {
            AdditionalProperties = []
        };
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        AgentMessage agentMessage = Assert.IsType<AgentMessage>(a2aResponse);
        Assert.Null(agentMessage.Metadata);
    }

    /// <summary>
    /// Verifies that when runMode is Message, the result is always an AgentMessage even when
    /// the agent would otherwise support background responses.
    /// </summary>
    [Fact]
    public async Task MapA2A_MessageMode_AlwaysReturnsAgentMessageAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        ITaskManager taskManager = CreateAgentMock(options => capturedOptions = options)
            .Object.MapA2A(runMode: AgentRunMode.DisallowBackground);

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        Assert.IsType<AgentMessage>(a2aResponse);
        Assert.NotNull(capturedOptions);
        Assert.False(capturedOptions.AllowBackgroundResponses);
    }

    /// <summary>
    /// Verifies that in BackgroundIfSupported mode when the agent completes immediately (no ContinuationToken),
    /// the result is an AgentMessage because the response type is determined solely by ContinuationToken presence.
    /// </summary>
    [Fact]
    public async Task MapA2A_BackgroundIfSupportedMode_WhenNoContinuationToken_ReturnsAgentMessageAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        ITaskManager taskManager = CreateAgentMock(options => capturedOptions = options)
            .Object.MapA2A(runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        Assert.IsType<AgentMessage>(a2aResponse);
        Assert.NotNull(capturedOptions);
        Assert.True(capturedOptions.AllowBackgroundResponses);
    }

    /// <summary>
    /// Verifies that a custom Dynamic delegate returning false produces an AgentMessage
    /// even when the agent completes immediately (no ContinuationToken).
    /// </summary>
    [Fact]
    public async Task MapA2A_DynamicMode_WithFalseCallback_ReturnsAgentMessageAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Quick reply")]);
        ITaskManager taskManager = CreateAgentMockWithResponse(response)
            .Object.MapA2A(runMode: AgentRunMode.AllowBackgroundWhen((_, _) => ValueTask.FromResult(false)));

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        Assert.IsType<AgentMessage>(a2aResponse);
    }

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

    /// <summary>
    /// Verifies that when the agent returns a ContinuationToken, an AgentTask in Working state is returned.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenResponseHasContinuationToken_ReturnsAgentTaskInWorkingStateAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Starting work...")])
        {
            ContinuationToken = CreateTestContinuationToken()
        };
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);
        Assert.Equal(TaskState.Working, agentTask.Status.State);
    }

    /// <summary>
    /// Verifies that when the agent returns a ContinuationToken, the returned task includes
    /// intermediate messages from the initial response in its status message.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenResponseHasContinuationToken_TaskStatusHasIntermediateMessageAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Starting work...")])
        {
            ContinuationToken = CreateTestContinuationToken()
        };
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);
        Assert.NotNull(agentTask.Status.Message);
        TextPart textPart = Assert.IsType<TextPart>(Assert.Single(agentTask.Status.Message.Parts));
        Assert.Equal("Starting work...", textPart.Text);
    }

    /// <summary>
    /// Verifies that when the agent returns a ContinuationToken, the continuation token
    /// is serialized into the AgentTask.Metadata for persistence.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenResponseHasContinuationToken_StoresTokenInTaskMetadataAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Starting work...")])
        {
            ContinuationToken = CreateTestContinuationToken()
        };
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);
        Assert.NotNull(agentTask.Metadata);
        Assert.True(agentTask.Metadata.ContainsKey("__a2a__continuationToken"));
    }

    /// <summary>
    /// Verifies that when a task is created (Working or Completed), the original user message
    /// is added to the task history, matching the A2A SDK's behavior when it creates tasks internally.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenTaskIsCreated_OriginalMessageIsInHistoryAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Starting work...")])
        {
            ContinuationToken = CreateTestContinuationToken()
        };
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();
        AgentMessage originalMessage = new() { MessageId = "user-msg-1", Role = MessageRole.User, Parts = [new TextPart { Text = "Do something" }] };

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = originalMessage
        });

        // Assert
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);
        Assert.NotNull(agentTask.History);
        Assert.Contains(agentTask.History, m => m.MessageId == "user-msg-1" && m.Role == MessageRole.User);
    }

    /// <summary>
    /// Verifies that in BackgroundIfSupported mode when the agent completes immediately (no ContinuationToken),
    /// the returned AgentMessage preserves the original context ID.
    /// </summary>
    [Fact]
    public async Task MapA2A_BackgroundIfSupportedMode_WhenNoContinuationToken_ReturnsAgentMessageWithContextIdAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Done!")]);
        ITaskManager taskManager = CreateAgentMockWithResponse(response)
            .Object.MapA2A(runMode: AgentRunMode.AllowBackgroundIfSupported);
        AgentMessage originalMessage = new() { MessageId = "user-msg-2", ContextId = "ctx-123", Role = MessageRole.User, Parts = [new TextPart { Text = "Quick task" }] };

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = originalMessage
        });

        // Assert
        AgentMessage agentMessage = Assert.IsType<AgentMessage>(a2aResponse);
        Assert.Equal("ctx-123", agentMessage.ContextId);
    }

    /// <summary>
    /// Verifies that when OnTaskUpdated is invoked on a task with a pending continuation token
    /// and the agent returns a completed response (null ContinuationToken), the task is updated to Completed.
    /// </summary>
    [Fact]
    public async Task MapA2A_OnTaskUpdated_WhenBackgroundOperationCompletes_TaskIsCompletedAsync()
    {
        // Arrange
        int callCount = 0;
        Mock<AIAgent> agentMock = CreateAgentMockWithSequentialResponses(
            // First call: return response with ContinuationToken (long-running)
            new AgentResponse([new ChatMessage(ChatRole.Assistant, "Starting...")])
            {
                ContinuationToken = CreateTestContinuationToken()
            },
            // Second call (via OnTaskUpdated): return completed response
            new AgentResponse([new ChatMessage(ChatRole.Assistant, "Done!")]),
            ref callCount);
        ITaskManager taskManager = agentMock.Object.MapA2A();

        // Act — trigger OnMessageReceived to create the task
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);
        Assert.Equal(TaskState.Working, agentTask.Status.State);

        // Act — invoke OnTaskUpdated to check on the background operation
        await InvokeOnTaskUpdatedAsync(taskManager, agentTask);

        // Assert — task should now be completed
        AgentTask? updatedTask = await taskManager.GetTaskAsync(new TaskQueryParams { Id = agentTask.Id }, CancellationToken.None);
        Assert.NotNull(updatedTask);
        Assert.Equal(TaskState.Completed, updatedTask.Status.State);
        Assert.NotNull(updatedTask.Artifacts);
        Artifact artifact = Assert.Single(updatedTask.Artifacts);
        TextPart textPart = Assert.IsType<TextPart>(Assert.Single(artifact.Parts));
        Assert.Equal("Done!", textPart.Text);
    }

    /// <summary>
    /// Verifies that when OnTaskUpdated is invoked on a task with a pending continuation token
    /// and the agent returns another ContinuationToken, the task stays in Working state.
    /// </summary>
    [Fact]
    public async Task MapA2A_OnTaskUpdated_WhenBackgroundOperationStillWorking_TaskRemainsWorkingAsync()
    {
        // Arrange
        int callCount = 0;
        Mock<AIAgent> agentMock = CreateAgentMockWithSequentialResponses(
            // First call: return response with ContinuationToken
            new AgentResponse([new ChatMessage(ChatRole.Assistant, "Starting...")])
            {
                ContinuationToken = CreateTestContinuationToken()
            },
            // Second call (via OnTaskUpdated): still working, return another token
            new AgentResponse([new ChatMessage(ChatRole.Assistant, "Still working...")])
            {
                ContinuationToken = CreateTestContinuationToken()
            },
            ref callCount);
        ITaskManager taskManager = agentMock.Object.MapA2A();

        // Act — trigger OnMessageReceived to create the task
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);

        // Act — invoke OnTaskUpdated; agent still working
        await InvokeOnTaskUpdatedAsync(taskManager, agentTask);

        // Assert — task should still be in Working state
        AgentTask? updatedTask = await taskManager.GetTaskAsync(new TaskQueryParams { Id = agentTask.Id }, CancellationToken.None);
        Assert.NotNull(updatedTask);
        Assert.Equal(TaskState.Working, updatedTask.Status.State);
    }

    /// <summary>
    /// Verifies the full lifecycle: agent starts background work, first poll returns still working,
    /// second poll returns completed.
    /// </summary>
    [Fact]
    public async Task MapA2A_OnTaskUpdated_MultiplePolls_EventuallyCompletesAsync()
    {
        // Arrange
        int callCount = 0;
        Mock<AIAgent> agentMock = CreateAgentMockWithCallCount(ref callCount, invocation =>
        {
            return invocation switch
            {
                // First call: start background work
                1 => new AgentResponse([new ChatMessage(ChatRole.Assistant, "Starting...")])
                {
                    ContinuationToken = CreateTestContinuationToken()
                },
                // Second call: still working
                2 => new AgentResponse([new ChatMessage(ChatRole.Assistant, "Still working...")])
                {
                    ContinuationToken = CreateTestContinuationToken()
                },
                // Third call: done
                _ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "All done!")])
            };
        });
        ITaskManager taskManager = agentMock.Object.MapA2A();

        // Act — create the task
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Do work" }] }
        });
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);
        Assert.Equal(TaskState.Working, agentTask.Status.State);

        // Act — first poll: still working
        AgentTask? currentTask = await taskManager.GetTaskAsync(new TaskQueryParams { Id = agentTask.Id }, CancellationToken.None);
        Assert.NotNull(currentTask);
        await InvokeOnTaskUpdatedAsync(taskManager, currentTask);
        currentTask = await taskManager.GetTaskAsync(new TaskQueryParams { Id = agentTask.Id }, CancellationToken.None);
        Assert.NotNull(currentTask);
        Assert.Equal(TaskState.Working, currentTask.Status.State);

        // Act — second poll: completed
        await InvokeOnTaskUpdatedAsync(taskManager, currentTask);
        currentTask = await taskManager.GetTaskAsync(new TaskQueryParams { Id = agentTask.Id }, CancellationToken.None);
        Assert.NotNull(currentTask);
        Assert.Equal(TaskState.Completed, currentTask.Status.State);

        // Assert — final output as artifact
        Assert.NotNull(currentTask.Artifacts);
        Artifact artifact = Assert.Single(currentTask.Artifacts);
        TextPart textPart = Assert.IsType<TextPart>(Assert.Single(artifact.Parts));
        Assert.Equal("All done!", textPart.Text);
    }

    /// <summary>
    /// Verifies that when the agent throws during a background operation poll,
    /// the task is updated to Failed state.
    /// </summary>
    [Fact]
    public async Task MapA2A_OnTaskUpdated_WhenAgentThrows_TaskIsFailedAsync()
    {
        // Arrange
        int callCount = 0;
        Mock<AIAgent> agentMock = CreateAgentMockWithCallCount(ref callCount, invocation =>
        {
            if (invocation == 1)
            {
                return new AgentResponse([new ChatMessage(ChatRole.Assistant, "Starting...")])
                {
                    ContinuationToken = CreateTestContinuationToken()
                };
            }

            throw new InvalidOperationException("Agent failed");
        });
        ITaskManager taskManager = agentMock.Object.MapA2A();

        // Act — create the task
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);

        // Act — poll the task; agent throws
        await Assert.ThrowsAsync<InvalidOperationException>(() => InvokeOnTaskUpdatedAsync(taskManager, agentTask));

        // Assert — task should be Failed
        AgentTask? updatedTask = await taskManager.GetTaskAsync(new TaskQueryParams { Id = agentTask.Id }, CancellationToken.None);
        Assert.NotNull(updatedTask);
        Assert.Equal(TaskState.Failed, updatedTask.Status.State);
    }

    /// <summary>
    /// Verifies that in Task mode with a ContinuationToken, the result is an AgentTask in Working state.
    /// </summary>
    [Fact]
    public async Task MapA2A_TaskMode_WhenContinuationToken_ReturnsWorkingAgentTaskAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Working on it...")])
        {
            ContinuationToken = CreateTestContinuationToken()
        };
        ITaskManager taskManager = CreateAgentMockWithResponse(response)
            .Object.MapA2A(runMode: AgentRunMode.AllowBackgroundIfSupported);

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);
        Assert.Equal(TaskState.Working, agentTask.Status.State);
        Assert.NotNull(agentTask.Metadata);
        Assert.True(agentTask.Metadata.ContainsKey("__a2a__continuationToken"));
    }

    /// <summary>
    /// Verifies that when the agent returns a ContinuationToken with no progress messages,
    /// the task transitions to Working state with a null status message.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenContinuationTokenWithNoMessages_TaskStatusHasNullMessageAsync()
    {
        // Arrange
        AgentResponse response = new([])
        {
            ContinuationToken = CreateTestContinuationToken()
        };
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);
        Assert.Equal(TaskState.Working, agentTask.Status.State);
        Assert.Null(agentTask.Status.Message);
    }

    /// <summary>
    /// Verifies that when OnTaskUpdated is invoked on a completed task with a follow-up message
    /// and no continuation token in metadata, the task processes history and completes with a new artifact.
    /// </summary>
    [Fact]
    public async Task MapA2A_OnTaskUpdated_WhenNoContinuationToken_ProcessesHistoryAndCompletesAsync()
    {
        // Arrange
        int callCount = 0;
        Mock<AIAgent> agentMock = CreateAgentMockWithCallCount(ref callCount, invocation =>
        {
            return invocation switch
            {
                // First call: create a task with ContinuationToken
                1 => new AgentResponse([new ChatMessage(ChatRole.Assistant, "Starting...")])
                {
                    ContinuationToken = CreateTestContinuationToken()
                },
                // Second call (via OnTaskUpdated): complete the background operation
                2 => new AgentResponse([new ChatMessage(ChatRole.Assistant, "Done!")]),
                // Third call (follow-up via OnTaskUpdated): complete follow-up
                _ => new AgentResponse([new ChatMessage(ChatRole.Assistant, "Follow-up done!")])
            };
        });
        ITaskManager taskManager = agentMock.Object.MapA2A();

        // Act — create a working task (with continuation token)
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);

        // Act — first OnTaskUpdated: completes the background operation
        await InvokeOnTaskUpdatedAsync(taskManager, agentTask);
        agentTask = (await taskManager.GetTaskAsync(new TaskQueryParams { Id = agentTask.Id }, CancellationToken.None))!;
        Assert.Equal(TaskState.Completed, agentTask.Status.State);

        // Simulate a follow-up message by adding it to history and re-submitting via OnTaskUpdated
        agentTask.History ??= [];
        agentTask.History.Add(new AgentMessage { MessageId = "follow-up", Role = MessageRole.User, Parts = [new TextPart { Text = "Follow up" }] });

        // Act — invoke OnTaskUpdated without a continuation token in metadata
        await InvokeOnTaskUpdatedAsync(taskManager, agentTask);

        // Assert
        AgentTask? updatedTask = await taskManager.GetTaskAsync(new TaskQueryParams { Id = agentTask.Id }, CancellationToken.None);
        Assert.NotNull(updatedTask);
        Assert.Equal(TaskState.Completed, updatedTask.Status.State);
        Assert.NotNull(updatedTask.Artifacts);
        Assert.Equal(2, updatedTask.Artifacts.Count);
        Artifact artifact = updatedTask.Artifacts[1];
        TextPart textPart = Assert.IsType<TextPart>(Assert.Single(artifact.Parts));
        Assert.Equal("Follow-up done!", textPart.Text);
    }

    /// <summary>
    /// Verifies that when a task is cancelled, the continuation token is removed from metadata.
    /// </summary>
    [Fact]
    public async Task MapA2A_OnTaskCancelled_RemovesContinuationTokenFromMetadataAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Starting...")])
        {
            ContinuationToken = CreateTestContinuationToken()
        };
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();

        // Act — create a working task with a continuation token
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);
        Assert.NotNull(agentTask.Metadata);
        Assert.True(agentTask.Metadata.ContainsKey("__a2a__continuationToken"));

        // Act — cancel the task
        await taskManager.CancelTaskAsync(new TaskIdParams { Id = agentTask.Id }, CancellationToken.None);

        // Assert — continuation token should be removed from metadata
        Assert.False(agentTask.Metadata.ContainsKey("__a2a__continuationToken"));
    }

    /// <summary>
    /// Verifies that when the agent throws an OperationCanceledException during a poll,
    /// it is re-thrown without marking the task as Failed.
    /// </summary>
    [Fact]
    public async Task MapA2A_OnTaskUpdated_WhenOperationCancelled_DoesNotMarkFailedAsync()
    {
        // Arrange
        int callCount = 0;
        Mock<AIAgent> agentMock = CreateAgentMockWithCallCount(ref callCount, invocation =>
        {
            if (invocation == 1)
            {
                return new AgentResponse([new ChatMessage(ChatRole.Assistant, "Starting...")])
                {
                    ContinuationToken = CreateTestContinuationToken()
                };
            }

            throw new OperationCanceledException("Cancelled");
        });
        ITaskManager taskManager = agentMock.Object.MapA2A();

        // Act — create the task
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });
        AgentTask agentTask = Assert.IsType<AgentTask>(a2aResponse);

        // Act — poll the task; agent throws OperationCanceledException
        await Assert.ThrowsAsync<OperationCanceledException>(() => InvokeOnTaskUpdatedAsync(taskManager, agentTask));

        // Assert — task should still be Working, not Failed
        AgentTask? updatedTask = await taskManager.GetTaskAsync(new TaskQueryParams { Id = agentTask.Id }, CancellationToken.None);
        Assert.NotNull(updatedTask);
        Assert.Equal(TaskState.Working, updatedTask.Status.State);
    }

    /// <summary>
    /// Verifies that when the incoming message has a ContextId, it is used for the task
    /// rather than generating a new one.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenMessageHasContextId_UsesProvidedContextIdAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Reply")]);
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage
            {
                MessageId = "test-id",
                ContextId = "my-context-123",
                Role = MessageRole.User,
                Parts = [new TextPart { Text = "Hello" }]
            }
        });

        // Assert
        AgentMessage agentMessage = Assert.IsType<AgentMessage>(a2aResponse);
        Assert.Equal("my-context-123", agentMessage.ContextId);
    }

#pragma warning restore MEAI001

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

    private static async Task<A2AResponse> InvokeOnMessageReceivedAsync(ITaskManager taskManager, MessageSendParams messageSendParams)
    {
        Func<MessageSendParams, CancellationToken, Task<A2AResponse>>? handler = taskManager.OnMessageReceived;
        Assert.NotNull(handler);
        return await handler.Invoke(messageSendParams, CancellationToken.None);
    }

    private static async Task InvokeOnTaskUpdatedAsync(ITaskManager taskManager, AgentTask agentTask)
    {
        Func<AgentTask, CancellationToken, Task>? handler = taskManager.OnTaskUpdated;
        Assert.NotNull(handler);
        await handler.Invoke(agentTask, CancellationToken.None);
    }

#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
    private static ResponseContinuationToken CreateTestContinuationToken()
    {
        return ResponseContinuationToken.FromBytes(new byte[] { 0x01, 0x02, 0x03 });
    }
#pragma warning restore MEAI001

    private static Mock<AIAgent> CreateAgentMockWithSequentialResponses(
        AgentResponse firstResponse,
        AgentResponse secondResponse,
        ref int callCount)
    {
        return CreateAgentMockWithCallCount(ref callCount, invocation =>
            invocation == 1 ? firstResponse : secondResponse);
    }

    private static Mock<AIAgent> CreateAgentMockWithCallCount(
        ref int callCount,
        Func<int, AgentResponse> responseFactory)
    {
        // Use a StrongBox to allow the lambda to capture a mutable reference
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

    private sealed class TestAgentSession : AgentSession;
}
