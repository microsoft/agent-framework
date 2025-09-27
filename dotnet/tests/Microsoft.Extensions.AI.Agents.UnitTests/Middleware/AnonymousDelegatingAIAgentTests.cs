// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests.Middleware;

/// <summary>
/// Unit tests for the <see cref="AnonymousDelegatingAIAgent"/> class.
/// </summary>
public class AnonymousDelegatingAIAgentTests
{
    private readonly Mock<AIAgent> _innerAgentMock;
    private readonly List<ChatMessage> _testMessages;
    private readonly AgentThread _testThread;
    private readonly AgentRunOptions _testOptions;
    private readonly AgentRunResponse _testResponse;
    private readonly AgentRunResponseUpdate[] _testStreamingResponses;

    public AnonymousDelegatingAIAgentTests()
    {
        this._innerAgentMock = new Mock<AIAgent>();
        this._testMessages = [new ChatMessage(ChatRole.User, "Test message")];
        this._testThread = new AgentThread();
        this._testOptions = new AgentRunOptions();
        this._testResponse = new AgentRunResponse([new ChatMessage(ChatRole.Assistant, "Test response")]);
        this._testStreamingResponses = [
            new AgentRunResponseUpdate(ChatRole.Assistant, "Response 1"),
            new AgentRunResponseUpdate(ChatRole.Assistant, "Response 2")
        ];

        this._innerAgentMock.Setup(x => x.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread?>(),
                It.IsAny<AgentRunOptions?>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(this._testResponse);

        this._innerAgentMock.Setup(x => x.RunStreamingAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread?>(),
                It.IsAny<AgentRunOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(ToAsyncEnumerableAsync(this._testStreamingResponses));
    }

    #region Constructor Tests

    /// <summary>
    /// Verify that constructor throws ArgumentNullException when innerAgent is null.
    /// </summary>
    [Fact]
    public void Constructor_WithNullInnerAgent_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("innerAgent", () =>
            new AnonymousDelegatingAIAgent(null!, (_, _, _, _, _) => Task.CompletedTask));
    }

    /// <summary>
    /// Verify that constructor throws ArgumentNullException when sharedFunc is null.
    /// </summary>
    [Fact]
    public void Constructor_WithNullSharedFunc_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>("sharedFunc", () =>
            new AnonymousDelegatingAIAgent(this._innerAgentMock.Object, null!));
    }

    /// <summary>
    /// Verify that constructor throws ArgumentNullException when both delegates are null.
    /// </summary>
    [Fact]
    public void Constructor_WithBothDelegatesNull_ThrowsArgumentNullException()
    {
        // Act & Assert
        var exception = Assert.Throws<ArgumentNullException>(() =>
            new AnonymousDelegatingAIAgent(this._innerAgentMock.Object, null, null));

        Assert.Contains("runFunc", exception.Message);
    }

    /// <summary>
    /// Verify that constructor succeeds with valid sharedFunc.
    /// </summary>
    [Fact]
    public void Constructor_WithValidSharedFunc_Succeeds()
    {
        // Act
        var agent = new AnonymousDelegatingAIAgent(this._innerAgentMock.Object, (_, _, _, _, _) => Task.CompletedTask);

        // Assert
        Assert.NotNull(agent);
    }

    /// <summary>
    /// Verify that constructor succeeds with valid runFunc only.
    /// </summary>
    [Fact]
    public void Constructor_WithValidRunFunc_Succeeds()
    {
        // Act
        var agent = new AnonymousDelegatingAIAgent(
            this._innerAgentMock.Object,
            (_, _, _, _, _) => Task.FromResult(this._testResponse),
            null);

        // Assert
        Assert.NotNull(agent);
    }

    /// <summary>
    /// Verify that constructor succeeds with valid runStreamingFunc only.
    /// </summary>
    [Fact]
    public void Constructor_WithValidRunStreamingFunc_Succeeds()
    {
        // Act
        var agent = new AnonymousDelegatingAIAgent(
            this._innerAgentMock.Object,
            null,
            (_, _, _, _, _) => ToAsyncEnumerableAsync(this._testStreamingResponses));

        // Assert
        Assert.NotNull(agent);
    }

    /// <summary>
    /// Verify that constructor succeeds with both runFunc and runStreamingFunc.
    /// </summary>
    [Fact]
    public void Constructor_WithBothRunAndStreamingFunc_Succeeds()
    {
        // Act
        var agent = new AnonymousDelegatingAIAgent(
            this._innerAgentMock.Object,
            (_, _, _, _, _) => Task.FromResult(this._testResponse),
            (_, _, _, _, _) => ToAsyncEnumerableAsync(this._testStreamingResponses));

        // Assert
        Assert.NotNull(agent);
    }

    #endregion

    #region Shared Function Tests

    /// <summary>
    /// Verify that shared function receives correct context and calls inner agent.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithSharedFunc_ContextPropagatedAsync()
    {
        // Arrange
        IEnumerable<ChatMessage>? capturedMessages = null;
        AgentThread? capturedThread = null;
        AgentRunOptions? capturedOptions = null;
        CancellationToken capturedCancellationToken = default;
        var expectedCancellationToken = new CancellationToken(true);

        var agent = new AnonymousDelegatingAIAgent(this._innerAgentMock.Object,
            async (messages, thread, options, next, cancellationToken) =>
            {
                capturedMessages = messages;
                capturedThread = thread;
                capturedOptions = options;
                capturedCancellationToken = cancellationToken;
                await next(messages, thread, options, cancellationToken);
            });

        // Act
        await agent.RunAsync(this._testMessages, this._testThread, this._testOptions, expectedCancellationToken);

        // Assert
        Assert.Same(this._testMessages, capturedMessages);
        Assert.Same(this._testThread, capturedThread);
        Assert.Same(this._testOptions, capturedOptions);
        Assert.Equal(expectedCancellationToken, capturedCancellationToken);

        this._innerAgentMock.Verify(x => x.RunAsync(
            this._testMessages,
            this._testThread,
            this._testOptions,
            expectedCancellationToken), Times.Once);
    }

    /// <summary>
    /// Verify that shared function works for both RunAsync and RunStreamingAsync.
    /// </summary>
    [Fact]
    public async Task SharedFunc_WorksForBothRunAndStreamingAsync()
    {
        // Arrange
        var callCount = 0;
        var agent = new AnonymousDelegatingAIAgent(this._innerAgentMock.Object,
            async (messages, thread, options, next, cancellationToken) =>
            {
                callCount++;
                await next(messages, thread, options, cancellationToken);
            });

        // Act
        await agent.RunAsync(this._testMessages, this._testThread, this._testOptions);
        var streamingResults = await agent.RunStreamingAsync(this._testMessages, this._testThread, this._testOptions).ToListAsync();

        // Assert
        Assert.Equal(2, callCount);
        Assert.NotNull(streamingResults);
        Assert.Equal(this._testStreamingResponses.Length, streamingResults.Count);
    }

    #endregion

    #region Separate Delegate Tests

    /// <summary>
    /// Verify that RunAsync with runFunc only uses the runFunc.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithRunFuncOnly_UsesRunFuncAsync()
    {
        // Arrange
        var runFuncCalled = false;
        var agent = new AnonymousDelegatingAIAgent(
            this._innerAgentMock.Object,
            (messages, thread, options, innerAgent, cancellationToken) =>
            {
                runFuncCalled = true;
                return innerAgent.RunAsync(messages, thread, options, cancellationToken);
            },
            null);

        // Act
        var result = await agent.RunAsync(this._testMessages, this._testThread, this._testOptions);

        // Assert
        Assert.True(runFuncCalled);
        Assert.Same(this._testResponse, result);
    }

    /// <summary>
    /// Verify that RunStreamingAsync with runFunc only converts from runFunc.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_WithRunFuncOnly_ConvertsFromRunFuncAsync()
    {
        // Arrange
        var runFuncCalled = false;
        var agent = new AnonymousDelegatingAIAgent(
            this._innerAgentMock.Object,
            (messages, thread, options, innerAgent, cancellationToken) =>
            {
                runFuncCalled = true;
                return innerAgent.RunAsync(messages, thread, options, cancellationToken);
            },
            null);

        // Act
        var results = await agent.RunStreamingAsync(this._testMessages, this._testThread, this._testOptions).ToListAsync();

        // Assert
        Assert.True(runFuncCalled);
        Assert.NotEmpty(results);
    }

    /// <summary>
    /// Verify that RunAsync with runStreamingFunc only converts from runStreamingFunc.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithStreamingFuncOnly_ConvertsFromStreamingFuncAsync()
    {
        // Arrange
        var streamingFuncCalled = false;
        var agent = new AnonymousDelegatingAIAgent(
            this._innerAgentMock.Object,
            null,
            (messages, thread, options, innerAgent, cancellationToken) =>
            {
                streamingFuncCalled = true;
                return innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken);
            });

        // Act
        var result = await agent.RunAsync(this._testMessages, this._testThread, this._testOptions);

        // Assert
        Assert.True(streamingFuncCalled);
        Assert.NotNull(result);
    }

    /// <summary>
    /// Verify that RunStreamingAsync with runStreamingFunc only uses the runStreamingFunc.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_WithStreamingFuncOnly_UsesStreamingFuncAsync()
    {
        // Arrange
        var streamingFuncCalled = false;
        var agent = new AnonymousDelegatingAIAgent(
            this._innerAgentMock.Object,
            null,
            (messages, thread, options, innerAgent, cancellationToken) =>
            {
                streamingFuncCalled = true;
                return innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken);
            });

        // Act
        var results = await agent.RunStreamingAsync(this._testMessages, this._testThread, this._testOptions).ToListAsync();

        // Assert
        Assert.True(streamingFuncCalled);
        Assert.Equal(this._testStreamingResponses.Length, results.Count);
    }

    /// <summary>
    /// Verify that when both delegates are provided, each uses its respective implementation.
    /// </summary>
    [Fact]
    public async Task BothDelegates_EachUsesRespectiveImplementationAsync()
    {
        // Arrange
        var runFuncCalled = false;
        var streamingFuncCalled = false;

        var agent = new AnonymousDelegatingAIAgent(
            this._innerAgentMock.Object,
            (messages, thread, options, innerAgent, cancellationToken) =>
            {
                runFuncCalled = true;
                return innerAgent.RunAsync(messages, thread, options, cancellationToken);
            },
            (messages, thread, options, innerAgent, cancellationToken) =>
            {
                streamingFuncCalled = true;
                return innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken);
            });

        // Act
        await agent.RunAsync(this._testMessages, this._testThread, this._testOptions);
        await agent.RunStreamingAsync(this._testMessages, this._testThread, this._testOptions).ToListAsync();

        // Assert
        Assert.True(runFuncCalled);
        Assert.True(streamingFuncCalled);
    }

    #endregion

    #region Error Handling Tests

    /// <summary>
    /// Verify that exceptions from shared function are propagated.
    /// </summary>
    [Fact]
    public async Task SharedFunc_ThrowsException_PropagatesExceptionAsync()
    {
        // Arrange
        var expectedException = new InvalidOperationException("Test exception");
        var agent = new AnonymousDelegatingAIAgent(this._innerAgentMock.Object,
            (_, _, _, _, _) => throw expectedException);

        // Act & Assert
        var actualException = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync(this._testMessages, this._testThread, this._testOptions));

        Assert.Same(expectedException, actualException);
    }

    /// <summary>
    /// Verify that exceptions from runFunc are propagated.
    /// </summary>
    [Fact]
    public async Task RunFunc_ThrowsException_PropagatesExceptionAsync()
    {
        // Arrange
        var expectedException = new InvalidOperationException("Test exception");
        var agent = new AnonymousDelegatingAIAgent(
            this._innerAgentMock.Object,
            (_, _, _, _, _) => throw expectedException,
            null);

        // Act & Assert
        var actualException = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync(this._testMessages, this._testThread, this._testOptions));

        Assert.Same(expectedException, actualException);
    }

    /// <summary>
    /// Verify that exceptions from runStreamingFunc are propagated.
    /// </summary>
    [Fact]
    public async Task StreamingFunc_ThrowsException_PropagatesExceptionAsync()
    {
        // Arrange
        var expectedException = new InvalidOperationException("Test exception");
        var agent = new AnonymousDelegatingAIAgent(
            this._innerAgentMock.Object,
            null,
            (_, _, _, _, _) => throw expectedException);

        // Act & Assert
        var actualException = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in agent.RunStreamingAsync(this._testMessages, this._testThread, this._testOptions))
            {
                // Should throw before yielding any items
            }
        });

        Assert.Same(expectedException, actualException);
    }

    /// <summary>
    /// Verify that shared function that doesn't call inner agent throws InvalidOperationException.
    /// </summary>
    [Fact]
    public async Task SharedFunc_DoesNotCallInner_ThrowsInvalidOperationAsync()
    {
        // Arrange
        var agent = new AnonymousDelegatingAIAgent(this._innerAgentMock.Object,
            (_, _, _, _, _) => Task.CompletedTask); // Doesn't call next

        // Act & Assert
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync(this._testMessages, this._testThread, this._testOptions));

        Assert.Contains("without producing an AgentRunResponse", exception.Message);
    }

    #endregion

    #region AsyncLocal Context Tests

    /// <summary>
    /// Verify that AsyncLocal context is maintained across delegate boundaries.
    /// </summary>
    [Fact]
    public async Task AsyncLocalContext_MaintainedAcrossDelegatesAsync()
    {
        // Arrange
        var asyncLocal = new AsyncLocal<int>();
        var capturedValue = 0;

        var agent = new AnonymousDelegatingAIAgent(this._innerAgentMock.Object,
            async (messages, thread, options, next, cancellationToken) =>
            {
                asyncLocal.Value = 42;
                await next(messages, thread, options, cancellationToken);
                capturedValue = asyncLocal.Value;
            });

        this._innerAgentMock.Setup(x => x.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread?>(),
                It.IsAny<AgentRunOptions?>(),
                It.IsAny<CancellationToken>()))
            .Returns(() =>
            {
                // Verify AsyncLocal value is available in inner agent call
                Assert.Equal(42, asyncLocal.Value);
                return Task.FromResult(this._testResponse);
            });

        // Act
        Assert.Equal(0, asyncLocal.Value); // Initial value
        await agent.RunAsync(this._testMessages, this._testThread, this._testOptions);

        // Assert
        Assert.Equal(0, asyncLocal.Value); // Should be reset after call
        Assert.Equal(42, capturedValue); // But was maintained during call
    }

    #endregion

    #region Helper Methods

    private static async IAsyncEnumerable<T> ToAsyncEnumerableAsync<T>(IEnumerable<T> items)
    {
        foreach (var item in items)
        {
            await Task.Yield();
            yield return item;
        }
    }

    #endregion
}
