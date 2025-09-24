// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents.Runtime;
using Moq;

namespace Microsoft.Extensions.AI.Agents.Hosting.UnitTests;

/// <summary>
/// Tests for the <see cref="AgentProxy"/> constructor.
/// </summary>
public class AgentProxyTests
{
    /// <summary>
    /// Verifies that the constructor assigns the Name property correctly for various valid agent names.
    /// </summary>
    [Theory]
    [InlineData("agent")]
    [InlineData(" ")]
    [InlineData("特殊字符")]
    [InlineData("    a")]
    public void Constructor_ValidName_SetsNameProperty(string name)
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();

        // Act
        var proxy = new AgentProxy(name, mockClient.Object);

        // Assert
        Assert.Equal(name, proxy.Name);
    }

    /// <summary>
    /// Verifies that GetNewThread returns a non-null <see cref="AgentProxyThread"/> instance.
    /// </summary>
    [Fact]
    public void GetNewThread_WhenCalled_ReturnsNewAgentProxyThreadInstance()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var proxy = new AgentProxy("agentName", mockClient.Object);

        // Act
        AgentThread result = proxy.GetNewThread();

        // Assert
        Assert.NotNull(result);
        Assert.IsType<AgentProxyThread>(result);
    }

    /// <summary>
    /// Verifies that consecutive calls to GetNewThread return distinct instances.
    /// </summary>
    [Fact]
    public void GetNewThread_MultipleCalls_ReturnsDistinctInstances()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var proxy = new AgentProxy("agentName", mockClient.Object);

        // Act
        AgentThread first = proxy.GetNewThread();
        AgentThread second = proxy.GetNewThread();

        // Assert
        Assert.NotNull(first);
        Assert.NotNull(second);
        Assert.NotSame(first, second);
    }
    private const string AgentName = "agentName";
    private const string ThreadId = "thread1";
    private static readonly IReadOnlyCollection<ChatMessage> s_emptyMessages = [];

    private static bool IsValidGuid(string value) =>
        Guid.TryParse(value, out _);

    /// <summary>
    /// Verifies that RunAsync returns a deserialized AgentRunResponse when the actor response status is Completed.
    /// Input: empty messages, threadId, Completed status with empty JSON object.
    /// Expected: AgentRunResponse with no messages.
    /// </summary>
    [Fact]
    public async Task RunAsync_WhenStatusIsCompleted_ReturnsDeserializedResponseAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var mockHandle = new Mock<ActorResponseHandle>();
        var jsonElement = JsonDocument.Parse("{}").RootElement;
        var actorResponse = new ActorResponse
        {
            ActorId = new ActorId(AgentName, ThreadId),
            MessageId = "msg1",
            Data = jsonElement,
            Status = RequestStatus.Completed
        };
        mockHandle
            .Setup(h => h.GetResponseAsync(It.IsAny<CancellationToken>()))
            .Returns(new ValueTask<ActorResponse>(actorResponse));
        mockClient
            .Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(mockHandle.Object);

        var proxy = new AgentProxy(AgentName, mockClient.Object);
        var thread = proxy.GetNewThread(ThreadId);

        // Act
        var result = await proxy.RunAsync(s_emptyMessages, thread);

        // Assert
        Assert.NotNull(result);
        Assert.Empty(result.Messages);
    }

    /// <summary>
    /// Verifies that RunAsync throws an InvalidOperationException when the actor response status is Failed.
    /// Input: empty messages, threadId, Failed status.
    /// Expected: InvalidOperationException with message containing the response data.
    /// </summary>
    [Fact]
    public async Task RunAsync_WhenStatusIsFailed_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var mockHandle = new Mock<ActorResponseHandle>();
        var jsonElement = JsonDocument.Parse("{}").RootElement;
        var actorResponse = new ActorResponse
        {
            ActorId = new ActorId(AgentName, ThreadId),
            MessageId = "msg1",
            Data = jsonElement,
            Status = RequestStatus.Failed
        };
        mockHandle
            .Setup(h => h.GetResponseAsync(It.IsAny<CancellationToken>()))
            .Returns(new ValueTask<ActorResponse>(actorResponse));
        mockClient
            .Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(mockHandle.Object);

        var proxy = new AgentProxy(AgentName, mockClient.Object);
        var thread = proxy.GetNewThread(ThreadId);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            proxy.RunAsync(s_emptyMessages, thread));
        Assert.Equal("The agent run request failed: {}", exception.Message);
    }

    /// <summary>
    /// Verifies that RunAsync throws an InvalidOperationException when the actor response status is Pending.
    /// Input: empty messages, threadId, Pending status.
    /// Expected: InvalidOperationException with pending message.
    /// </summary>
    [Fact]
    public async Task RunAsync_WhenStatusIsPending_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var mockHandle = new Mock<ActorResponseHandle>();
        var jsonElement = JsonDocument.Parse("{}").RootElement;
        var actorResponse = new ActorResponse
        {
            ActorId = new ActorId(AgentName, ThreadId),
            MessageId = "msg1",
            Data = jsonElement,
            Status = RequestStatus.Pending
        };
        mockHandle
            .Setup(h => h.GetResponseAsync(It.IsAny<CancellationToken>()))
            .Returns(new ValueTask<ActorResponse>(actorResponse));
        mockClient
            .Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(mockHandle.Object);

        var proxy = new AgentProxy(AgentName, mockClient.Object);
        var thread = proxy.GetNewThread(ThreadId);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            proxy.RunAsync(s_emptyMessages, thread));
        Assert.Equal("The agent run request is still pending.", exception.Message);
    }

    /// <summary>
    /// Verifies that RunAsync throws a NotSupportedException when the actor response status is unsupported.
    /// Input: empty messages, threadId, NotFound status.
    /// Expected: NotSupportedException with unsupported status message.
    /// </summary>
    [Fact]
    public async Task RunAsync_WhenStatusIsUnsupported_ThrowsNotSupportedExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var mockHandle = new Mock<ActorResponseHandle>();
        var jsonElement = JsonDocument.Parse("{}").RootElement;
        var actorResponse = new ActorResponse
        {
            ActorId = new ActorId(AgentName, ThreadId),
            MessageId = "msg1",
            Data = jsonElement,
            Status = RequestStatus.NotFound
        };
        mockHandle
            .Setup(h => h.GetResponseAsync(It.IsAny<CancellationToken>()))
            .Returns(new ValueTask<ActorResponse>(actorResponse));
        mockClient
            .Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(mockHandle.Object);

        var proxy = new AgentProxy(AgentName, mockClient.Object);
        var thread = proxy.GetNewThread(ThreadId);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<NotSupportedException>(() =>
            proxy.RunAsync(s_emptyMessages, thread));
        Assert.Equal($"The agent run request returned an unsupported status: {RequestStatus.NotFound}.", exception.Message);
    }

    /// <summary>
    /// Verifies that passing an AgentThread that is not an AgentProxyThread to RunStreamingAsync throws an ArgumentException.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_InvalidThread_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var proxy = new AgentProxy("testAgent", mockClient.Object);
        AgentThread invalidThread = new Mock<AgentThread>().Object;

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentException>(async () =>
        {
            await foreach (var _ in proxy.RunStreamingAsync([], invalidThread, cancellationToken: CancellationToken.None))
            {
            }
        });
    }

    /// <summary>
    /// This test verifies that RunStreamingAsync completes without throwing when a valid AgentProxyThread is used.
    /// TODO: Mock IActorClient.SendRequestAsync to return an ActorResponseHandle whose WatchUpdatesAsync yields no updates.
    /// </summary>
    [Fact(Skip = "Mocking of ActorResponseHandle.WatchUpdatesAsync with IActorClient is required")]
    public async Task RunStreamingAsync_ValidProxyThread_CompletesSuccessfullyAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var proxy = new AgentProxy("testAgent", mockClient.Object);
        var proxyThread = new AgentProxyThread();

        // Act & Assert
        await foreach (var _ in proxy.RunStreamingAsync([], proxyThread, cancellationToken: CancellationToken.None))
        {
            // No items expected
        }
    }

    /// <summary>
    /// Verifies that RunStreamingAsync yields AgentRunResponseUpdate for pending status.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_PendingStatus_YieldsAgentRunResponseUpdateAsync()
    {
        // Arrange
        var messages = Array.Empty<ChatMessage>();
        const string ThreadId = "thread1";
        var expectedUpdate = new AgentRunResponseUpdate(ChatRole.Assistant, "response");

        var updateTypeInfo = AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponseUpdate));
        var jsonElement = JsonSerializer.SerializeToElement(expectedUpdate, updateTypeInfo);

        var actorUpdate = new ActorRequestUpdate(RequestStatus.Pending, jsonElement);
        var mockHandle = new Mock<ActorResponseHandle>();
        mockHandle
            .Setup(h => h.WatchUpdatesAsync(It.IsAny<CancellationToken>()))
            .Returns(GetAsyncEnumerableAsync(actorUpdate));
        var mockClient = new Mock<IActorClient>();
        mockClient
            .Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(mockHandle.Object);

        var proxy = new AgentProxy("agentName", mockClient.Object);
        var thread = proxy.GetNewThread(ThreadId);

        // Act
        var results = new List<AgentRunResponseUpdate>();
        await foreach (var update in proxy.RunStreamingAsync(messages, thread))
        {
            results.Add(update);
        }

        // Assert
        Assert.Single(results);
        Assert.Equal(expectedUpdate.Text, results[0].Text);
        Assert.Equal(expectedUpdate.Role, results[0].Role);
    }

    /// <summary>
    /// Verifies that RunStreamingAsync completes without yielding any updates when receiving only a completed status.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_CompletedStatus_YieldsNoUpdatesAsync()
    {
        // Arrange
        var messages = Array.Empty<ChatMessage>();
        const string ThreadId = "thread1";

        var agentRunResponse = new AgentRunResponse
        {
            Messages = [new(ChatRole.Assistant, "response")]
        };
        var responseTypeInfo = AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponse));
        var jsonElement = JsonSerializer.SerializeToElement(agentRunResponse, responseTypeInfo);

        var actorUpdate = new ActorRequestUpdate(RequestStatus.Completed, jsonElement);
        var mockHandle = new Mock<ActorResponseHandle>();
        mockHandle
            .Setup(h => h.WatchUpdatesAsync(It.IsAny<CancellationToken>()))
            .Returns(GetAsyncEnumerableAsync(actorUpdate));
        var mockClient = new Mock<IActorClient>();
        mockClient
            .Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(mockHandle.Object);

        var proxy = new AgentProxy("agentName", mockClient.Object);
        var thread = proxy.GetNewThread(ThreadId);

        // Act
        var results = new List<AgentRunResponseUpdate>();
        await foreach (var update in proxy.RunStreamingAsync(messages, thread))
        {
            results.Add(update);
        }

        // Assert
        Assert.Empty(results); // Completed status should not yield any updates
    }

    /// <summary>
    /// Verifies that RunStreamingAsync does not yield duplicate content when receiving both
    /// streaming updates and a completed message containing the same content.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_CompletedAfterUpdates_DoesNotYieldDuplicateContentAsync()
    {
        // Arrange: Create a scenario with streaming updates followed by completion
        var messages = Array.Empty<ChatMessage>();
        const string ThreadId = "thread1";

        var pendingUpdate = new AgentRunResponseUpdate(ChatRole.Assistant, "streaming response");
        var completedResponse = new AgentRunResponse
        {
            Messages = [new(ChatRole.Assistant, "streaming response")]
        };

        var updates = new List<ActorRequestUpdate>
        {
            new(RequestStatus.Pending, JsonSerializer.SerializeToElement(pendingUpdate,
                AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponseUpdate)))),
            new(RequestStatus.Completed, JsonSerializer.SerializeToElement(completedResponse,
                AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponse))))
        };

        var mockHandle = new Mock<ActorResponseHandle>();
        mockHandle
            .Setup(h => h.WatchUpdatesAsync(It.IsAny<CancellationToken>()))
            .Returns(GetAsyncEnumerableAsync(updates));
        var mockClient = new Mock<IActorClient>();
        mockClient
            .Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(mockHandle.Object);

        var proxy = new AgentProxy("agentName", mockClient.Object);
        var thread = proxy.GetNewThread(ThreadId);

        // Act
        var results = new List<AgentRunResponseUpdate>();
        await foreach (var update in proxy.RunStreamingAsync(messages, thread))
        {
            results.Add(update);
        }

        // Assert: Should only get the pending update, not duplicate content from completion
        Assert.Single(results);
        Assert.Equal("streaming response", results[0].Text);
        Assert.Equal(ChatRole.Assistant, results[0].Role);
    }

    private static async IAsyncEnumerable<ActorRequestUpdate> GetAsyncEnumerableAsync(ActorRequestUpdate update)
    {
        yield return update;
        await Task.CompletedTask;
    }

    private static async IAsyncEnumerable<ActorRequestUpdate> GetAsyncEnumerableAsync(List<ActorRequestUpdate> updates)
    {
        foreach (var update in updates)
        {
            yield return update;
            await Task.CompletedTask;
        }
    }

    /// <summary>
    /// Verifies that RunStreamingAsync throws InvalidOperationException when an update status is Failed.
    /// Uses a mock IActorClient to return a Failed update. Expected: InvalidOperationException is thrown.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_FailedStatus_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var messages = Array.Empty<ChatMessage>();
        const string ThreadId = "thread1";
        var expectedUpdate = new AgentRunResponseUpdate(ChatRole.Assistant, "response");
        var updateTypeInfo = AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponseUpdate));
        var jsonElement = JsonSerializer.SerializeToElement(expectedUpdate, updateTypeInfo);

        var actorUpdate = new ActorRequestUpdate(RequestStatus.Failed, jsonElement);
        var mockHandle = new Mock<ActorResponseHandle>();
        mockHandle
            .Setup(h => h.WatchUpdatesAsync(It.IsAny<CancellationToken>()))
            .Returns(GetAsyncEnumerableAsync(actorUpdate));
        var mockClient = new Mock<IActorClient>();
        mockClient
            .Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(mockHandle.Object);

        var proxy = new AgentProxy("agentName", mockClient.Object);
        var thread = proxy.GetNewThread(ThreadId);

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var update in proxy.RunStreamingAsync(messages, thread))
            {
                // force enumeration
            }
        });
        Assert.Contains("The agent run request failed", exception.Message);
    }

    /// <summary>
    /// Verifies that constructor throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public void Constructor_NullClient_ThrowsArgumentNullException() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentProxy("agentName", null!));

    /// <summary>
    /// Verifies that constructor throws ArgumentNullException when name is null.
    /// </summary>
    [Fact]
    public void Constructor_NullName_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentProxy(null!, mockClient.Object));
    }

    /// <summary>
    /// Verifies that constructor throws ArgumentException when name is empty.
    /// </summary>
    [Fact]
    public void Constructor_EmptyName_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => new AgentProxy("", mockClient.Object));
    }

    /// <summary>
    /// Verifies that RunAsync with thread overload validates null messages.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithThread_NullMessages_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var proxy = new AgentProxy("agentName", mockClient.Object);
        var thread = new AgentProxyThread();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(() =>
            proxy.RunAsync(messages: null!, thread, null, CancellationToken.None));
    }

    /// <summary>
    /// Verifies that RunAsync with thread overload throws for invalid thread type.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithInvalidThreadType_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var proxy = new AgentProxy("agentName", mockClient.Object);
        var invalidThread = new Mock<AgentThread>().Object;
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(() =>
            proxy.RunAsync(messages, invalidThread, null, CancellationToken.None));
        Assert.Contains("thread must be an instance of AgentProxyThread", exception.Message);
    }

    /// <summary>
    /// Verifies that RunAsync with thread overload creates new thread ID when thread is null.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithNullThread_CreatesNewThreadIdAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var mockHandle = new Mock<ActorResponseHandle>();
        var response = new AgentRunResponse { Messages = [] };
        var jsonElement = JsonSerializer.SerializeToElement(response,
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponse)));
        var actorResponse = new ActorResponse
        {
            ActorId = new ActorId(AgentName, ThreadId),
            MessageId = "msg1",
            Data = jsonElement,
            Status = RequestStatus.Completed
        };

        mockHandle.Setup(h => h.GetResponseAsync(It.IsAny<CancellationToken>()))
            .Returns(new ValueTask<ActorResponse>(actorResponse));

        mockClient.Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(mockHandle.Object);

        var proxy = new AgentProxy("agentName", mockClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        var result = await proxy.RunAsync(messages, thread: null, options: null, CancellationToken.None);

        // Assert
        Assert.NotNull(result);
        mockClient.Verify(c => c.SendRequestAsync(
            It.Is<ActorRequest>(r => !string.IsNullOrEmpty(r.ActorId.Key)),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verifies that RunAsync handles cancellation properly.
    /// </summary>
    [Fact]
    public async Task RunAsync_CancellationRequested_ThrowsOperationCanceledExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        mockClient.Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ThrowsAsync(new OperationCanceledException());

        var proxy = new AgentProxy("agentName", mockClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };
        var thread = proxy.GetNewThread(ThreadId);

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(() =>
            proxy.RunAsync(messages, thread, cancellationToken: cts.Token));
    }

    /// <summary>
    /// Verifies that RunStreamingAsync with thread overload validates null messages.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_WithThread_NullMessages_ThrowsArgumentNullExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var proxy = new AgentProxy("agentName", mockClient.Object);
        var thread = new AgentProxyThread();

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(async () =>
        {
            await foreach (var _ in proxy.RunStreamingAsync(messages: null!, thread, null, CancellationToken.None))
            {
                // force enumeration
            }
        });
    }

    /// <summary>
    /// Verifies that RunStreamingAsync with thread overload throws for invalid thread type.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_WithInvalidThreadType_ThrowsArgumentExceptionAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var proxy = new AgentProxy("agentName", mockClient.Object);
        var invalidThread = new Mock<AgentThread>().Object;
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act & Assert
        var exception = await Assert.ThrowsAsync<ArgumentException>(async () =>
        {
            await foreach (var _ in proxy.RunStreamingAsync(messages, invalidThread, null, CancellationToken.None))
            {
                // force enumeration
            }
        });
        Assert.Contains("thread must be an instance of AgentProxyThread", exception.Message);
    }

    /// <summary>
    /// Verifies that RunStreamingAsync handles cancellation during enumeration.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_CancellationDuringEnumeration_StopsEnumerationAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        using var cts = new CancellationTokenSource();

        var updates = new List<ActorRequestUpdate>
        {
            new(RequestStatus.Pending, JsonSerializer.SerializeToElement(
                new AgentRunResponseUpdate(ChatRole.Assistant, "1"),
                AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponseUpdate)))),
            new(RequestStatus.Pending, JsonSerializer.SerializeToElement(
                new AgentRunResponseUpdate(ChatRole.Assistant, "2"),
                AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponseUpdate))))
        };

        using var fakeHandle = new FakeActorResponseHandle(updates, cts);

        mockClient.Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(fakeHandle);

        var proxy = new AgentProxy("agentName", mockClient.Object);
        var thread = proxy.GetNewThread(ThreadId);
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        var receivedUpdates = new List<AgentRunResponseUpdate>();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
        {
            await foreach (var update in proxy.RunStreamingAsync(messages, thread, cancellationToken: cts.Token))
            {
                receivedUpdates.Add(update);
            }
        });

        // Assert
        Assert.Single(receivedUpdates); // Only first update should be received
    }

    /// <summary>
    /// Verifies that RunAsync correctly uses message ID from last message if available.
    /// </summary>
    [Fact]
    public async Task RunAsync_UsesLastMessageId_WhenAvailableAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var mockHandle = new Mock<ActorResponseHandle>();
        const string ExpectedMessageId = "custom-message-id";
        var response = new AgentRunResponse { Messages = [] };
        var jsonElement = JsonSerializer.SerializeToElement(response,
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponse)));
        var actorResponse = new ActorResponse
        {
            ActorId = new ActorId(AgentName, ThreadId),
            MessageId = ExpectedMessageId,
            Data = jsonElement,
            Status = RequestStatus.Completed
        };

        mockHandle.Setup(h => h.GetResponseAsync(It.IsAny<CancellationToken>()))
            .Returns(new ValueTask<ActorResponse>(actorResponse));

        mockClient.Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(mockHandle.Object);

        var proxy = new AgentProxy("agentName", mockClient.Object);
        var thread = proxy.GetNewThread(ThreadId);
        var messages = new List<ChatMessage>
        {
            new(ChatRole.User, "first"),
            new(ChatRole.User, "last") { MessageId = ExpectedMessageId }
        };

        // Act
        await proxy.RunAsync(messages, thread);

        // Assert
        mockClient.Verify(c => c.SendRequestAsync(
            It.Is<ActorRequest>(r => r.MessageId == ExpectedMessageId),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verifies that RunAsync generates new message ID when last message has no ID.
    /// </summary>
    [Fact]
    public async Task RunAsync_GeneratesMessageId_WhenLastMessageHasNoIdAsync()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var mockHandle = new Mock<ActorResponseHandle>();
        var response = new AgentRunResponse { Messages = [] };
        var jsonElement = JsonSerializer.SerializeToElement(response,
            AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponse)));
        var actorResponse = new ActorResponse
        {
            ActorId = new ActorId(AgentName, ThreadId),
            MessageId = "generated-id",
            Data = jsonElement,
            Status = RequestStatus.Completed
        };

        mockHandle.Setup(h => h.GetResponseAsync(It.IsAny<CancellationToken>()))
            .Returns(new ValueTask<ActorResponse>(actorResponse));

        mockClient.Setup(c => c.SendRequestAsync(It.IsAny<ActorRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(mockHandle.Object);

        var proxy = new AgentProxy("agentName", mockClient.Object);
        var thread = proxy.GetNewThread(ThreadId);
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await proxy.RunAsync(messages, thread);

        // Assert
        mockClient.Verify(c => c.SendRequestAsync(
            It.Is<ActorRequest>(r => !string.IsNullOrEmpty(r.MessageId) && IsValidGuid(r.MessageId)),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verifies that GetNewThread returns unique instances with unique IDs.
    /// </summary>
    [Fact]
    public void GetNewThread_MultipleCalls_ReturnsUniqueThreadsWithUniqueIds()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var proxy = new AgentProxy("agentName", mockClient.Object);
        var threads = new List<AgentThread>();

        // Act
        for (int i = 0; i < 10; i++)
        {
            threads.Add(proxy.GetNewThread());
        }

        // Assert
        var threadIds = threads.Cast<AgentProxyThread>().Select(t => t.ConversationId).ToList();
        Assert.Equal(10, threadIds.Count);
        Assert.Equal(10, threadIds.Distinct().Count()); // All IDs should be unique
    }

    /// <summary>
    /// Fake implementation of ActorResponseHandle for testing purposes.
    /// </summary>
    private sealed class FakeActorResponseHandle : ActorResponseHandle
    {
        private readonly List<ActorRequestUpdate> _updates;
        private readonly CancellationTokenSource _cancellationTokenSource;
        private readonly ActorResponse? _response;
        private readonly int _delayBetweenUpdates;

        public FakeActorResponseHandle(
            List<ActorRequestUpdate> updates,
            CancellationTokenSource cancellationTokenSource,
            ActorResponse? response = null,
            int delayBetweenUpdates = 10)
        {
            this._updates = updates;
            this._cancellationTokenSource = cancellationTokenSource;
            this._response = response;
            this._delayBetweenUpdates = delayBetweenUpdates;
        }

        public override bool TryGetResponse([System.Diagnostics.CodeAnalysis.NotNullWhen(true)] out ActorResponse? response)
        {
            response = this._response;
            return this._response is not null;
        }

        public override ValueTask<ActorResponse> GetResponseAsync(CancellationToken cancellationToken)
        {
            if (this._response is null)
            {
                throw new InvalidOperationException("No response configured");
            }
            return new ValueTask<ActorResponse>(this._response);
        }

        public override ValueTask CancelAsync(CancellationToken cancellationToken)
        {
            this._cancellationTokenSource.Cancel();
            return default;
        }

        public override async IAsyncEnumerable<ActorRequestUpdate> WatchUpdatesAsync([System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
        {
            for (int i = 0; i < this._updates.Count; i++)
            {
                cancellationToken.ThrowIfCancellationRequested();

                yield return this._updates[i];

                // Cancel after the first update
                if (i == 0)
                {
                    this._cancellationTokenSource.Cancel();
                }

                if (i < this._updates.Count - 1) // Don't delay after the last update
                {
                    await Task.Delay(this._delayBetweenUpdates, cancellationToken);
                }
            }
        }
    }
}
