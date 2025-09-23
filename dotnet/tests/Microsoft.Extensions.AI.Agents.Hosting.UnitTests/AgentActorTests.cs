// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Extensions.AI.Agents.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="AgentActor"/>.
/// </summary>
public class AgentActorTests
{
    /// <summary>
    /// Verifies that calling DisposeAsync completes successfully without throwing an exception.
    /// </summary>
    [Fact]
    public async Task DisposeAsync_NoException_CompletesSuccessfullyAsync()
    {
        var mockAgent = new Mock<AIAgent>();
        var mockContext = new Mock<IActorRuntimeContext>();
        var mockLogger = NullLoggerFactory.Instance.CreateLogger<AgentActor>();
        var actor = new AgentActor(mockAgent.Object, mockContext.Object, mockLogger);

        var valueTask = actor.DisposeAsync();

        Assert.True(valueTask.IsCompleted, "DisposeAsync should return a completed ValueTask.");
        await valueTask;
    }

    /// <summary>
    /// Verifies that when no thread state exists, GetNewThread is called.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithNoExistingThreadState_CallsGetNewThreadAsync()
    {
        var mockExpectedThread = new Mock<AgentThread>();

        var mockAgent = new Mock<AIAgent>();
        mockAgent.Setup(a => a.GetNewThread()).Returns(mockExpectedThread.Object);

        var mockContext = new Mock<IActorRuntimeContext>();
        var actorId = new ActorId("TestAgent", "test-instance");
        mockContext.Setup(c => c.ActorId).Returns(actorId);

        // Setup ReadAsync to return no existing thread state
        var readResponse = new ReadResponse("test-etag", [new GetValueResult(null)]);
        mockContext.Setup(c => c.ReadAsync(It.IsAny<ActorReadOperationBatch>(), It.IsAny<CancellationToken>()))
                   .ReturnsAsync(readResponse);

        // Setup WatchMessagesAsync to return empty sequence to prevent infinite loop
        mockContext.Setup(c => c.WatchMessagesAsync(It.IsAny<CancellationToken>()))
                   .Returns(CreateEmptyAsyncEnumerableAsync<ActorMessage>());

        var mockLogger = NullLoggerFactory.Instance.CreateLogger<AgentActor>();
        await using var actor = new AgentActor(mockAgent.Object, mockContext.Object, mockLogger);

        using var cts = new CancellationTokenSource();
        cts.CancelAfter(TimeSpan.FromMilliseconds(100)); // Cancel quickly to exit the loop

        await actor.RunAsync(cts.Token);

        mockAgent.Verify(a => a.GetNewThread(), Times.Once);
    }

    /// <summary>
    /// Verifies that when ReadAsync throws an exception, the actor handles it gracefully.
    /// </summary>
    [Fact]
    public async Task RunAsync_WhenReadAsyncThrows_HandlesExceptionGracefullyAsync()
    {
        var mockAgent = new Mock<AIAgent>();
        var mockContext = new Mock<IActorRuntimeContext>();
        var actorId = new ActorId("TestAgent", "test-instance");
        mockContext.Setup(c => c.ActorId).Returns(actorId);

        mockContext.Setup(c => c.ReadAsync(It.IsAny<ActorReadOperationBatch>(), It.IsAny<CancellationToken>()))
                   .ThrowsAsync(new InvalidOperationException("Read failed"));

        var mockLogger = NullLoggerFactory.Instance.CreateLogger<AgentActor>();
        await using var actor = new AgentActor(mockAgent.Object, mockContext.Object, mockLogger);

        using var cts = new CancellationTokenSource();

        await Assert.ThrowsAsync<InvalidOperationException>(async () =>
            await actor.RunAsync(cts.Token));

        mockAgent.Verify(a => a.GetNewThread(), Times.Never);
    }

    /// <summary>
    /// Verifies that the thread assignment works correctly when processing an agent request.
    /// This test checks that the thread used in the agent request is properly assigned.
    /// </summary>
    [Fact]
    public async Task HandleAgentRequest_UsesCorrectThreadAsync()
    {
        var threadJson = JsonSerializer.SerializeToElement(new { conversationId = "expected-thread-id" });
        var mockThread = new Mock<AgentThread>();

        var testAgent = new TestAgent();
        testAgent.ThreadForCreate = mockThread.Object;

        var mockContext = new Mock<IActorRuntimeContext>();
        var actorId = new ActorId("TestAgent", "test-instance");
        mockContext.Setup(c => c.ActorId).Returns(actorId);

        var readResponse = new ReadResponse("test-etag", [new GetValueResult(threadJson)]);
        mockContext.Setup(c => c.ReadAsync(It.IsAny<ActorReadOperationBatch>(), It.IsAny<CancellationToken>()))
                   .ReturnsAsync(readResponse);

        // Create a request message
        var requestMessage = new ActorRequestMessage("test-message-id")
        {
            SenderId = actorId,
            Method = AgentActorConstants.RunMethodName,
            Params = JsonSerializer.SerializeToElement(new AgentRunRequest
            {
                Messages = [new ChatMessage(ChatRole.User, "Test message")]
            })
        };

        var messageSequence = CreateAsyncEnumerableAsync(new List<ActorMessage> { requestMessage });
        mockContext.Setup(c => c.WatchMessagesAsync(It.IsAny<CancellationToken>()))
                   .Returns(messageSequence);

        mockContext.Setup(c => c.WriteAsync(It.IsAny<ActorWriteOperationBatch>(), It.IsAny<CancellationToken>()))
                   .ReturnsAsync(new WriteResponse("new-etag", true));

        var mockLogger = NullLoggerFactory.Instance.CreateLogger<AgentActor>();
        await using var actor = new AgentActor(testAgent, mockContext.Object, mockLogger);

        using var cts = new CancellationTokenSource();

        cts.CancelAfter(TimeSpan.FromSeconds(1));

        await actor.RunAsync(cts.Token);

        Assert.True(testAgent.RunStreamingAsyncCalled, "RunStreamingAsync should have been called");

        // Verify the thread was used in RunStreamingAsync and has the expected ID
        Assert.NotNull(testAgent.ThreadUsedInRunStreamingAsync);
        Assert.Same(mockThread.Object, testAgent.ThreadUsedInRunStreamingAsync);
        Assert.Equal(threadJson, testAgent.ElementUsedInDeserializeThread);
    }

    /// <summary>
    /// Helper method to create an empty async enumerable.
    /// </summary>
    private static async IAsyncEnumerable<T> CreateEmptyAsyncEnumerableAsync<T>()
    {
        await Task.CompletedTask;
        yield break;
    }

    /// <summary>
    /// Helper method to create an async enumerable from a list.
    /// </summary>
    private static async IAsyncEnumerable<T> CreateAsyncEnumerableAsync<T>(IEnumerable<T> items)
    {
        foreach (var item in items)
        {
            yield return item;
        }
    }

    /// <summary>
    /// Test agent implementation to track method calls.
    /// </summary>
    private sealed class TestAgent : AIAgent
    {
        public AgentThread? ThreadForCreate { get; set; }
        public JsonElement? ElementUsedInDeserializeThread { get; set; }
        public bool RunStreamingAsyncCalled { get; private set; }
        public AgentThread? ThreadUsedInRunStreamingAsync { get; private set; }

        public override AgentThread GetNewThread()
        {
            return this.ThreadForCreate!;
        }

        public override AgentThread DeserializeThread(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
        {
            this.ElementUsedInDeserializeThread = serializedThread;
            return this.ThreadForCreate!;
        }

        public override Task<AgentRunResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
        {
            this.ThreadUsedInRunStreamingAsync = thread;
            return Task.FromResult(new AgentRunResponse
            {
                Messages = [new ChatMessage(ChatRole.Assistant, "Test response")]
            });
        }

        public override async IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            this.RunStreamingAsyncCalled = true;
            this.ThreadUsedInRunStreamingAsync = thread;

            yield return new AgentRunResponseUpdate(ChatRole.Assistant, "Test response");
            await Task.CompletedTask;
        }
    }
}
