// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AnonymousDelegatingAIAgent"/> class.
/// </summary>
public class AnonymousDelegatingAIAgentTests
{
    private readonly Mock<AIAgent> _innerAgentMock;
    private readonly List<ChatMessage> _testMessages;
    private readonly AgentThread _testThread;
    private readonly AgentRunOptions _testOptions;
    private readonly AgentResponse _testResponse;
    private readonly AgentResponseUpdate[] _testStreamingResponses;

    public AnonymousDelegatingAIAgentTests()
    {
        this._innerAgentMock = new Mock<AIAgent>();
        this._testMessages = [new ChatMessage(ChatRole.User, "Test message")];
        this._testThread = new Mock<AgentThread>().Object;
        this._testOptions = new AgentRunOptions();
        this._testResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Test response")]);
        this._testStreamingResponses = [
            new AgentResponseUpdate(ChatRole.Assistant, "Response 1"),
            new AgentResponseUpdate(ChatRole.Assistant, "Response 2")
        ];

        this._innerAgentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentThread?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(this._testResponse);

        this._innerAgentMock
            .Protected()
            .Setup<IAsyncEnumerable<AgentResponseUpdate>>("RunCoreStreamingAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentThread?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
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

        this._innerAgentMock
            .Protected()
            .Verify<Task<AgentResponse>>("RunCoreAsync",
                Times.Once(),
                ItExpr.Is<IEnumerable<ChatMessage>>(m => m == this._testMessages),
                ItExpr.Is<AgentThread?>(t => t == this._testThread),
                ItExpr.Is<AgentRunOptions?>(o => o == this._testOptions),
                ItExpr.Is<CancellationToken>(ct => ct == expectedCancellationToken));
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

        Assert.Contains("without producing an AgentResponse", exception.Message);
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

        this._innerAgentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentThread?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
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

    #region Multiple Middleware Chaining Tests

    /// <summary>
    /// Verify that multiple middleware execute in correct order (outer-to-inner, then inner-to-outer).
    /// </summary>
    [Fact]
    public async Task MultipleMiddleware_ExecuteInCorrectOrderAsync()
    {
        // Arrange
        var executionOrder = new List<string>();

        var outerAgent = new AnonymousDelegatingAIAgent(this._innerAgentMock.Object,
            async (messages, thread, options, next, cancellationToken) =>
            {
                executionOrder.Add("Outer-Pre");
                await next(messages, thread, options, cancellationToken);
                executionOrder.Add("Outer-Post");
            });

        var middleAgent = new AnonymousDelegatingAIAgent(outerAgent,
            async (messages, thread, options, next, cancellationToken) =>
            {
                executionOrder.Add("Middle-Pre");
                await next(messages, thread, options, cancellationToken);
                executionOrder.Add("Middle-Post");
            });

        var innerAgent = new AnonymousDelegatingAIAgent(middleAgent,
            async (messages, thread, options, next, cancellationToken) =>
            {
                executionOrder.Add("Inner-Pre");
                await next(messages, thread, options, cancellationToken);
                executionOrder.Add("Inner-Post");
            });

        // Act
        await innerAgent.RunAsync(this._testMessages, this._testThread, this._testOptions);

        // Assert
        var expectedOrder = new[] { "Inner-Pre", "Middle-Pre", "Outer-Pre", "Outer-Post", "Middle-Post", "Inner-Post" };
        Assert.Equal(expectedOrder, executionOrder);
    }

    /// <summary>
    /// Verify that multiple middleware with separate delegates execute in correct order.
    /// </summary>
    [Fact]
    public async Task MultipleMiddleware_SeparateDelegates_ExecuteInCorrectOrderAsync()
    {
        // Arrange
        var executionOrder = new List<string>();

        var outerAgent = new AnonymousDelegatingAIAgent(this._innerAgentMock.Object,
            (messages, thread, options, innerAgent, cancellationToken) =>
            {
                executionOrder.Add("Outer-Run");
                return innerAgent.RunAsync(messages, thread, options, cancellationToken);
            },
            (messages, thread, options, innerAgent, cancellationToken) =>
            {
                executionOrder.Add("Outer-Streaming");
                return innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken);
            });

        var middleAgent = new AnonymousDelegatingAIAgent(outerAgent,
            (messages, thread, options, innerAgent, cancellationToken) =>
            {
                executionOrder.Add("Middle-Run");
                return innerAgent.RunAsync(messages, thread, options, cancellationToken);
            },
            (messages, thread, options, innerAgent, cancellationToken) =>
            {
                executionOrder.Add("Middle-Streaming");
                return innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken);
            });

        // Act
        await middleAgent.RunAsync(this._testMessages, this._testThread, this._testOptions);
        await middleAgent.RunStreamingAsync(this._testMessages, this._testThread, this._testOptions).ToListAsync();

        // Assert
        Assert.Contains("Middle-Run", executionOrder);
        Assert.Contains("Outer-Run", executionOrder);
        Assert.Contains("Middle-Streaming", executionOrder);
        Assert.Contains("Outer-Streaming", executionOrder);

        var runIndex = executionOrder.IndexOf("Middle-Run");
        var outerRunIndex = executionOrder.IndexOf("Outer-Run");
        var streamingIndex = executionOrder.IndexOf("Middle-Streaming");
        var outerStreamingIndex = executionOrder.IndexOf("Outer-Streaming");

        Assert.True(runIndex < outerRunIndex);
        Assert.True(streamingIndex < outerStreamingIndex);
    }

    /// <summary>
    /// Verify that middleware can capture and modify parameters during execution.
    /// </summary>
    [Fact]
    public async Task MultipleMiddleware_ContextModification_PropagatedAsync()
    {
        // Arrange
        var capturedOptions = new List<AgentRunOptions?>();
        var executionOrder = new List<string>();

        var outerAgent = new AnonymousDelegatingAIAgent(this._innerAgentMock.Object,
            async (messages, thread, options, next, cancellationToken) =>
            {
                executionOrder.Add("Outer-Pre");
                await next(messages, thread, options, cancellationToken);
                executionOrder.Add("Outer-Post");
            });

        var innerAgent = new AnonymousDelegatingAIAgent(outerAgent,
            async (messages, thread, options, next, cancellationToken) =>
            {
                executionOrder.Add("Inner-Pre");
                capturedOptions.Add(options);
                await next(messages, thread, options, cancellationToken);
                executionOrder.Add("Inner-Post");
            });

        // Act
        await innerAgent.RunAsync(this._testMessages, this._testThread, this._testOptions);

        // Assert
        Assert.Single(capturedOptions);
        Assert.Same(this._testOptions, capturedOptions[0]); // Inner middleware sees original options
        var expectedOrder = new[] { "Inner-Pre", "Outer-Pre", "Outer-Post", "Inner-Post" };
        Assert.Equal(expectedOrder, executionOrder);
    }

    #endregion

    #region Error Handling in Chains Tests

    /// <summary>
    /// Verify that exceptions in middleware chains are properly propagated.
    /// </summary>
    [Fact]
    public async Task MultipleMiddleware_ExceptionInMiddle_PropagatesAsync()
    {
        // Arrange
        var expectedException = new InvalidOperationException("Middle middleware error");
        var outerExecuted = false;
        var innerExecuted = false;

        var outerAgent = new AnonymousDelegatingAIAgent(this._innerAgentMock.Object,
            async (messages, thread, options, next, cancellationToken) =>
            {
                outerExecuted = true;
                await next(messages, thread, options, cancellationToken);
            });

        var middleAgent = new AnonymousDelegatingAIAgent(outerAgent,
            (_, _, _, _, _) => throw expectedException);

        var innerAgent = new AnonymousDelegatingAIAgent(middleAgent,
            async (messages, thread, options, next, cancellationToken) =>
            {
                innerExecuted = true;
                await next(messages, thread, options, cancellationToken);
            });

        // Act & Assert
        var actualException = await Assert.ThrowsAsync<InvalidOperationException>(
            () => innerAgent.RunAsync(this._testMessages, this._testThread, this._testOptions));

        Assert.Same(expectedException, actualException);
        Assert.True(innerExecuted); // Inner middleware should execute
        Assert.False(outerExecuted); // Outer middleware should not execute due to exception
    }

    /// <summary>
    /// Verify that exceptions in streaming middleware chains are properly propagated.
    /// </summary>
    [Fact]
    public async Task MultipleMiddleware_ExceptionInStreaming_PropagatesAsync()
    {
        // Arrange
        var expectedException = new InvalidOperationException("Streaming middleware error");

        var outerAgent = new AnonymousDelegatingAIAgent(this._innerAgentMock.Object,
            null,
            (_, _, _, _, _) => throw expectedException);

        var innerAgent = new AnonymousDelegatingAIAgent(outerAgent,
            null,
            (messages, thread, options, innerAgent, cancellationToken) =>
                innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken));

        // Act & Assert
        var actualException = await Assert.ThrowsAsync<InvalidOperationException>(async () =>
        {
            await foreach (var _ in innerAgent.RunStreamingAsync(this._testMessages, this._testThread, this._testOptions))
            {
                // Should throw before yielding any items
            }
        });

        Assert.Same(expectedException, actualException);
    }

    #endregion

    #region Multiple Middleware Chaining Tests

    /// <summary>
    /// Verify that multiple middleware using AIAgentBuilder.Use() execute in correct order.
    /// </summary>
    [Fact]
    public async Task AIAgentBuilder_Use_MultipleMiddleware_ExecutesInCorrectOrderAsync()
    {
        // Arrange
        var executionOrder = new List<string>();

        var agent = new AIAgentBuilder(this._innerAgentMock.Object)
            .Use(async (messages, thread, options, next, cancellationToken) =>
            {
                executionOrder.Add("First-Pre");
                await next(messages, thread, options, cancellationToken);
                executionOrder.Add("First-Post");
            })
            .Use(async (messages, thread, options, next, cancellationToken) =>
            {
                executionOrder.Add("Second-Pre");
                await next(messages, thread, options, cancellationToken);
                executionOrder.Add("Second-Post");
            })
            .Build();

        // Act
        await agent.RunAsync(this._testMessages, this._testThread, this._testOptions);

        // Assert
        var expectedOrder = new[] { "First-Pre", "Second-Pre", "Second-Post", "First-Post" };
        Assert.Equal(expectedOrder, executionOrder);
    }

    /// <summary>
    /// Verify that multiple middleware with separate run/streaming delegates execute correctly.
    /// </summary>
    [Fact]
    public async Task AIAgentBuilder_Use_MultipleMiddlewareWithSeparateDelegates_ExecutesCorrectlyAsync()
    {
        // Arrange
        var runExecutionOrder = new List<string>();
        var streamingExecutionOrder = new List<string>();

        static async IAsyncEnumerable<AgentResponseUpdate> FirstStreamingMiddlewareAsync(
            IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, AIAgent innerAgent,
            [EnumeratorCancellation] CancellationToken cancellationToken,
            List<string> executionOrder)
        {
            executionOrder.Add("First-Streaming-Pre");
            await foreach (var update in innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken))
            {
                yield return update;
            }
            executionOrder.Add("First-Streaming-Post");
        }

        static async IAsyncEnumerable<AgentResponseUpdate> SecondStreamingMiddlewareAsync(
            IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, AIAgent innerAgent,
            [EnumeratorCancellation] CancellationToken cancellationToken,
            List<string> executionOrder)
        {
            executionOrder.Add("Second-Streaming-Pre");
            await foreach (var update in innerAgent.RunStreamingAsync(messages, thread, options, cancellationToken))
            {
                yield return update;
            }
            executionOrder.Add("Second-Streaming-Post");
        }

        var agent = new AIAgentBuilder(this._innerAgentMock.Object)
            .Use(
                async (messages, thread, options, innerAgent, cancellationToken) =>
                {
                    runExecutionOrder.Add("First-Run-Pre");
                    var result = await innerAgent.RunAsync(messages, thread, options, cancellationToken);
                    runExecutionOrder.Add("First-Run-Post");
                    return result;
                },
                (messages, thread, options, innerAgent, cancellationToken) =>
                    FirstStreamingMiddlewareAsync(messages, thread, options, innerAgent, cancellationToken, streamingExecutionOrder))
            .Use(
                async (messages, thread, options, innerAgent, cancellationToken) =>
                {
                    runExecutionOrder.Add("Second-Run-Pre");
                    var result = await innerAgent.RunAsync(messages, thread, options, cancellationToken);
                    runExecutionOrder.Add("Second-Run-Post");
                    return result;
                },
                (messages, thread, options, innerAgent, cancellationToken) =>
                    SecondStreamingMiddlewareAsync(messages, thread, options, innerAgent, cancellationToken, streamingExecutionOrder))
            .Build();

        // Act
        await agent.RunAsync(this._testMessages, this._testThread, this._testOptions);
        await agent.RunStreamingAsync(this._testMessages, this._testThread, this._testOptions).ToListAsync();

        // Assert
        var expectedRunOrder = new[] { "First-Run-Pre", "Second-Run-Pre", "Second-Run-Post", "First-Run-Post" };
        var expectedStreamingOrder = new[] { "First-Streaming-Pre", "Second-Streaming-Pre", "Second-Streaming-Post", "First-Streaming-Post" };

        Assert.Equal(expectedRunOrder, runExecutionOrder);
        Assert.Equal(expectedStreamingOrder, streamingExecutionOrder);
    }

    /// <summary>
    /// Verify that middleware can modify messages and options before passing to next middleware.
    /// </summary>
    [Fact]
    public async Task AIAgentBuilder_Use_MiddlewareModifiesContext_ChangesPropagateAsync()
    {
        // Arrange
        IEnumerable<ChatMessage>? capturedMessages = null;
        AgentRunOptions? capturedOptions = null;

        var agent = new AIAgentBuilder(this._innerAgentMock.Object)
            .Use(async (messages, thread, options, next, cancellationToken) =>
            {
                // Modify messages and options
                var modifiedMessages = messages.Concat([new ChatMessage(ChatRole.System, "Added by first middleware")]);
                var modifiedOptions = new AgentRunOptions();
                await next(modifiedMessages, thread, modifiedOptions, cancellationToken);
            })
            .Use(async (messages, thread, options, next, cancellationToken) =>
            {
                // Capture what the second middleware receives
                capturedMessages = messages;
                capturedOptions = options;
                await next(messages, thread, options, cancellationToken);
            })
            .Build();

        // Act
        await agent.RunAsync(this._testMessages, this._testThread, this._testOptions);

        // Assert
        Assert.NotNull(capturedMessages);
        Assert.NotNull(capturedOptions);
        Assert.Equal(2, capturedMessages.Count()); // Original + added message
        Assert.Contains(capturedMessages, m => m.Text == "Added by first middleware");
    }

    #endregion

    #region Error Handling in Chains Tests

    /// <summary>
    /// Verify that exceptions in middleware chains are properly propagated.
    /// </summary>
    [Fact]
    public async Task AIAgentBuilder_Use_ExceptionInMiddlewareChain_PropagatesCorrectlyAsync()
    {
        // Arrange
        var expectedException = new InvalidOperationException("Test exception from middleware");
        var executionOrder = new List<string>();

        var agent = new AIAgentBuilder(this._innerAgentMock.Object)
            .Use(async (messages, thread, options, next, cancellationToken) =>
            {
                executionOrder.Add("First-Pre");
                try
                {
                    await next(messages, thread, options, cancellationToken);
                    executionOrder.Add("First-Post-Success");
                }
                catch
                {
                    executionOrder.Add("First-Post-Exception");
                    throw;
                }
            })
            .Use(async (messages, thread, options, next, cancellationToken) =>
            {
                executionOrder.Add("Second-Pre");
                throw expectedException;
            })
            .Build();

        // Act & Assert
        var actualException = await Assert.ThrowsAsync<InvalidOperationException>(
            () => agent.RunAsync(this._testMessages, this._testThread, this._testOptions));

        Assert.Same(expectedException, actualException);
        var expectedOrder = new[] { "First-Pre", "Second-Pre", "First-Post-Exception" };
        Assert.Equal(expectedOrder, executionOrder);
    }

    /// <summary>
    /// Verify that middleware can handle and recover from exceptions in the chain.
    /// </summary>
    [Fact]
    public async Task AIAgentBuilder_Use_MiddlewareHandlesException_RecoveryWorksAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var fallbackResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Fallback response")]);

        var agent = new AIAgentBuilder(this._innerAgentMock.Object)
            .Use(
                async (messages, thread, options, innerAgent, cancellationToken) =>
                {
                    executionOrder.Add("Handler-Pre");
                    try
                    {
                        return await innerAgent.RunAsync(messages, thread, options, cancellationToken);
                    }
                    catch (InvalidOperationException)
                    {
                        executionOrder.Add("Handler-Caught-Exception");
                        return fallbackResponse;
                    }
                },
                null)
            .Use(async (messages, thread, options, next, cancellationToken) =>
            {
                executionOrder.Add("Throwing-Pre");
                throw new InvalidOperationException("Simulated error");
            })
            .Build();

        // Act
        var result = await agent.RunAsync(this._testMessages, this._testThread, this._testOptions);

        // Assert
        Assert.Same(fallbackResponse, result);
        var expectedOrder = new[] { "Handler-Pre", "Throwing-Pre", "Handler-Caught-Exception" };
        Assert.Equal(expectedOrder, executionOrder);
    }

    /// <summary>
    /// Verify that cancellation tokens are properly propagated through middleware chains.
    /// </summary>
    [Fact]
    public async Task AIAgentBuilder_Use_CancellationTokenPropagation_WorksCorrectlyAsync()
    {
        // Arrange
        var expectedToken = new CancellationToken(true);
        var capturedTokens = new List<CancellationToken>();

        // Setup mock to throw OperationCanceledException when cancelled token is used
        this._innerAgentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentThread?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.Is<CancellationToken>(ct => ct.IsCancellationRequested))
            .ThrowsAsync(new OperationCanceledException());

        var agent = new AIAgentBuilder(this._innerAgentMock.Object)
            .Use(async (messages, thread, options, next, cancellationToken) =>
            {
                capturedTokens.Add(cancellationToken);
                await next(messages, thread, options, cancellationToken);
            })
            .Use(async (messages, thread, options, next, cancellationToken) =>
            {
                capturedTokens.Add(cancellationToken);
                await next(messages, thread, options, cancellationToken);
            })
            .Build();

        // Act & Assert
        await Assert.ThrowsAsync<OperationCanceledException>(
            () => agent.RunAsync(this._testMessages, this._testThread, this._testOptions, expectedToken));

        Assert.All(capturedTokens, token => Assert.Equal(expectedToken, token));
        Assert.Equal(2, capturedTokens.Count);
    }

    /// <summary>
    /// Verify that middleware can short-circuit the chain by not calling next.
    /// </summary>
    [Fact]
    public async Task AIAgentBuilder_Use_MiddlewareShortCircuits_InnerAgentNotCalledAsync()
    {
        // Arrange
        var shortCircuitResponse = new AgentResponse([new ChatMessage(ChatRole.Assistant, "Short-circuited")]);
        var executionOrder = new List<string>();

        var agent = new AIAgentBuilder(this._innerAgentMock.Object)
            .Use(
                async (messages, thread, options, innerAgent, cancellationToken) =>
                {
                    executionOrder.Add("First-Pre");
                    var result = await innerAgent.RunAsync(messages, thread, options, cancellationToken);
                    executionOrder.Add("First-Post");
                    return result;
                },
                null)
            .Use(
                async (messages, thread, options, innerAgent, cancellationToken) =>
                {
                    executionOrder.Add("Second-ShortCircuit");
                    // Don't call inner agent - short circuit the chain
                    return shortCircuitResponse;
                },
                null)
            .Build();

        // Act
        var result = await agent.RunAsync(this._testMessages, this._testThread, this._testOptions);

        // Assert
        Assert.Same(shortCircuitResponse, result);
        var expectedOrder = new[] { "First-Pre", "Second-ShortCircuit", "First-Post" };
        Assert.Equal(expectedOrder, executionOrder);

        // Verify inner agent was never called
        this._innerAgentMock
            .Protected()
            .Verify<Task<AgentResponse>>("RunCoreAsync",
                Times.Never(),
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentThread?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>());
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
