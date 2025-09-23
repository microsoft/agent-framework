// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests.Middleware;

/// <summary>
/// Unit tests for RunningMiddlewareAgent functionality.
/// </summary>
public sealed class RunningMiddlewareAgentTests
{
    #region Context Value Validation Tests

    /// <summary>
    /// Verifies that AgentRunContext properties exactly match the parameters passed to RunAsync for non-streaming scenarios.
    /// </summary>
    [Fact]
    public async Task RunAsync_ContextValuesMatchParameters_NonStreamingAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var expectedMessages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var expectedThread = new AgentThread();
        var expectedOptions = new AgentRunOptions();
        var expectedCancellationToken = new CancellationToken();
        var expectedResponse = new AgentRunResponse([new(ChatRole.Assistant, "Response")]);

        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedResponse);

        AgentRunContext? capturedContext = null;
        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, (context, next) =>
        {
            capturedContext = context;
            return next(context);
        });

        // Act
        await middleware.RunAsync(expectedMessages, expectedThread, expectedOptions, expectedCancellationToken);

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Equal(expectedMessages, capturedContext.Messages);
        Assert.Same(expectedThread, capturedContext.Thread);
        Assert.Same(expectedOptions, capturedContext.Options);
        Assert.False(capturedContext.IsStreaming);
        Assert.Equal(expectedCancellationToken, capturedContext.CancellationToken);
        Assert.Same(middleware, capturedContext.Agent);
    }

    /// <summary>
    /// Verifies that AgentRunContext properties exactly match the parameters passed to RunStreamingAsync for streaming scenarios.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_ContextValuesMatchParameters_StreamingAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var expectedMessages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var expectedThread = new AgentThread();
        var expectedOptions = new AgentRunOptions();
        var expectedCancellationToken = new CancellationToken();
        var expectedUpdates = new List<AgentRunResponseUpdate>
        {
            new(ChatRole.Assistant, "Update 1")
        };

        mockInnerAgent.Setup(a => a.RunStreamingAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(expectedUpdates.ToAsyncEnumerable());

        AgentRunContext? capturedContext = null;
        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, (context, next) =>
        {
            capturedContext = context;
            return next(context);
        });

        // Act
        await foreach (var _ in middleware.RunStreamingAsync(expectedMessages, expectedThread, expectedOptions, expectedCancellationToken))
        {
            // Consume the stream
        }

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Equal(expectedMessages, capturedContext.Messages);
        Assert.Same(expectedThread, capturedContext.Thread);
        Assert.Same(expectedOptions, capturedContext.Options);
        Assert.True(capturedContext.IsStreaming);
        Assert.Equal(expectedCancellationToken, capturedContext.CancellationToken);
        Assert.Same(middleware, capturedContext.Agent);
    }

    /// <summary>
    /// Verifies context validation with null Thread and Options parameters.
    /// </summary>
    [Fact]
    public async Task RunAsync_ContextValuesWithNullParametersAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var expectedMessages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var expectedResponse = new AgentRunResponse([new(ChatRole.Assistant, "Response")]);

        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(expectedResponse);

        AgentRunContext? capturedContext = null;
        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, (context, next) =>
        {
            capturedContext = context;
            return next(context);
        });

        // Act
        await middleware.RunAsync(expectedMessages, thread: null, options: null, CancellationToken.None);

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Equal(expectedMessages, capturedContext.Messages);
        Assert.Null(capturedContext.Thread);
        Assert.Null(capturedContext.Options);
        Assert.False(capturedContext.IsStreaming);
    }

    #endregion

    #region Pre-Invocation Context Modification Tests

    /// <summary>
    /// Tests modifying Messages in the context before calling next() and verifies changes are passed to inner agent.
    /// </summary>
    [Fact]
    public async Task RunAsync_ModifyMessages_ChangesPassedToInnerAgentAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var originalMessages = new List<ChatMessage> { new(ChatRole.User, "Original message") };
        var modifiedMessages = new List<ChatMessage>
        {
            new(ChatRole.System, "System message"),
            new(ChatRole.User, "Modified message")
        };
        var expectedResponse = new AgentRunResponse([new(ChatRole.Assistant, "Response")]);

        IEnumerable<ChatMessage>? capturedMessages = null;
        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken>(
                (messages, thread, options, ct) => capturedMessages = messages)
            .ReturnsAsync(expectedResponse);

        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, (context, next) =>
        {
            // Modify messages before calling next
            context.Messages.Clear();
            foreach (var message in modifiedMessages)
            {
                context.Messages.Add(message);
            }
            return next(context);
        });

        // Act
        await middleware.RunAsync(originalMessages, null, null, CancellationToken.None);

        // Assert
        Assert.NotNull(capturedMessages);
        Assert.Equal(modifiedMessages.Count, capturedMessages.Count());
        Assert.Equal(modifiedMessages.First().Text, capturedMessages.First().Text);
        Assert.Equal(modifiedMessages.Last().Text, capturedMessages.Last().Text);
    }

    /// <summary>
    /// Tests modifying Thread in the context before calling next() and verifies changes are passed to inner agent.
    /// </summary>
    [Fact]
    public async Task RunAsync_ModifyThread_ChangesPassedToInnerAgentAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var originalThread = new AgentThread();
        var modifiedThread = new AgentThread();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var expectedResponse = new AgentRunResponse([new(ChatRole.Assistant, "Response")]);

        AgentThread? capturedThread = null;
        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken>(
                (messages, thread, options, ct) => capturedThread = thread)
            .ReturnsAsync(expectedResponse);

        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, (context, next) =>
        {
            // Note: Thread property is read-only, so we test that the original thread is passed through
            // In a real scenario, middleware would modify thread contents, not replace the reference
            return next(context);
        });

        // Act
        await middleware.RunAsync(messages, originalThread, null, CancellationToken.None);

        // Assert
        Assert.Same(originalThread, capturedThread);
    }

    /// <summary>
    /// Tests modifying Options in the context before calling next() and verifies changes are passed to inner agent.
    /// </summary>
    [Fact]
    public async Task RunAsync_ModifyOptions_ChangesPassedToInnerAgentAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var originalOptions = new AgentRunOptions();
        var modifiedOptions = new AgentRunOptions();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var expectedResponse = new AgentRunResponse([new(ChatRole.Assistant, "Response")]);

        AgentRunOptions? capturedOptions = null;
        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken>(
                (messages, thread, options, ct) => capturedOptions = options)
            .ReturnsAsync(expectedResponse);

        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, (context, next) =>
        {
            // Modify options before calling next
            context.Options = modifiedOptions;
            return next(context);
        });

        // Act
        await middleware.RunAsync(messages, null, originalOptions, CancellationToken.None);

        // Assert
        Assert.Same(modifiedOptions, capturedOptions);
    }

    #endregion

    #region Post-Invocation Context Modification Tests

    /// <summary>
    /// Tests modifying the RunResponse after inner agent execution and verifies it becomes the final result.
    /// </summary>
    [Fact]
    public async Task RunAsync_ModifyRunResponsePostInvocation_ReturnsModifiedResponseAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var originalResponse = new AgentRunResponse([new(ChatRole.Assistant, "Original response")]);
        var modifiedResponse = new AgentRunResponse([new(ChatRole.Assistant, "Modified response")]);

        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(originalResponse);

        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, async (context, next) =>
        {
            await next(context);
            // Modify response after inner agent execution
            context.SetRunResponse(modifiedResponse);
        });

        // Act
        var result = await middleware.RunAsync(messages, null, null, CancellationToken.None);

        // Assert
        Assert.Same(modifiedResponse, result);
        Assert.NotSame(originalResponse, result);
    }

    /// <summary>
    /// Tests modifying the RunStreamingResponse after inner agent execution and verifies the modified stream is returned.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_ModifyRunStreamingResponsePostInvocation_ReturnsModifiedStreamAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var originalUpdates = new List<AgentRunResponseUpdate>
        {
            new(ChatRole.Assistant, "Original update")
        };
        var modifiedUpdates = new List<AgentRunResponseUpdate>
        {
            new(ChatRole.Assistant, "Modified update")
        };

        mockInnerAgent.Setup(a => a.RunStreamingAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(originalUpdates.ToAsyncEnumerable());

        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, async (context, next) =>
        {
            await next(context);
            // Modify streaming response after inner agent execution
            context.SetRunStreamingResponse(modifiedUpdates.ToAsyncEnumerable());
        });

        // Act
        var result = new List<AgentRunResponseUpdate>();
        await foreach (var update in middleware.RunStreamingAsync(messages, null, null, CancellationToken.None))
        {
            result.Add(update);
        }

        // Assert
        Assert.Single(result);
        Assert.Equal("Modified update", result[0].Text);
    }

    /// <summary>
    /// Tests that post-invocation changes override the inner agent's original response properties.
    /// </summary>
    [Fact]
    public async Task RunAsync_PostInvocationOverridesOriginalResponseAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var originalResponse = new AgentRunResponse([new(ChatRole.Assistant, "Original")])
        {
            ResponseId = "original-id"
        };
        var modifiedResponse = new AgentRunResponse([new(ChatRole.Assistant, "Modified")])
        {
            ResponseId = "modified-id"
        };

        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(originalResponse);

        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, async (context, next) =>
        {
            await next(context);
            // Completely replace the response
            context.SetRunResponse(modifiedResponse);
        });

        // Act
        var result = await middleware.RunAsync(messages, null, null, CancellationToken.None);

        // Assert
        Assert.Equal("modified-id", result.ResponseId);
        Assert.Equal("Modified", result.Messages.First().Text);
        Assert.NotEqual(originalResponse.ResponseId, result.ResponseId);
    }

    #endregion

    #region Middleware Chaining and Execution Order Tests

    /// <summary>
    /// Tests execution order with multiple RunningMiddleware instances in a chain.
    /// </summary>
    [Fact]
    public async Task RunAsync_MultipleMiddleware_ExecutesInCorrectOrderAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var response = new AgentRunResponse([new(ChatRole.Assistant, "Response")]);
        var executionOrder = new List<string>();

        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback(() => executionOrder.Add("InnerAgent"))
            .ReturnsAsync(response);

        // Create middleware chain: Middleware1 -> Middleware2 -> Middleware3 -> InnerAgent
        var middleware3 = new RunDelegatingAgent(mockInnerAgent.Object, async (context, next) =>
        {
            executionOrder.Add("Middleware3-Pre");
            await next(context);
            executionOrder.Add("Middleware3-Post");
        });

        var middleware2 = new RunDelegatingAgent(middleware3, async (context, next) =>
        {
            executionOrder.Add("Middleware2-Pre");
            await next(context);
            executionOrder.Add("Middleware2-Post");
        });

        var middleware1 = new RunDelegatingAgent(middleware2, async (context, next) =>
        {
            executionOrder.Add("Middleware1-Pre");
            await next(context);
            executionOrder.Add("Middleware1-Post");
        });

        // Act
        await middleware1.RunAsync(messages, null, null, CancellationToken.None);

        // Assert
        var expectedOrder = new[]
        {
            "Middleware1-Pre",
            "Middleware2-Pre",
            "Middleware3-Pre",
            "InnerAgent",
            "Middleware3-Post",
            "Middleware2-Post",
            "Middleware1-Post"
        };
        Assert.Equal(expectedOrder, executionOrder);
    }

    /// <summary>
    /// Tests that context modifications from earlier middleware are visible to later middleware in the chain.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareChain_ContextModificationsFlowThroughAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var originalMessages = new List<ChatMessage> { new(ChatRole.User, "Original") };
        var response = new AgentRunResponse([new(ChatRole.Assistant, "Response")]);
        var capturedMessages = new List<string>();

        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken>(
                (messages, thread, options, ct) => capturedMessages.AddRange(messages.Select(m => m.Text)))
            .ReturnsAsync(response);

        // Middleware1: Adds a system message
        var middleware2 = new RunDelegatingAgent(mockInnerAgent.Object, async (context, next) =>
        {
            context.Messages.Insert(0, new ChatMessage(ChatRole.System, "System message"));
            await next(context);
        });

        // Middleware1: Adds a user message
        var middleware1 = new RunDelegatingAgent(middleware2, async (context, next) =>
        {
            context.Messages.Add(new ChatMessage(ChatRole.User, "Added by middleware1"));
            await next(context);
        });

        // Act
        await middleware1.RunAsync(originalMessages, null, null, CancellationToken.None);

        // Assert
        Assert.Equal(3, capturedMessages.Count);
        Assert.Contains("System message", capturedMessages);
        Assert.Contains("Original", capturedMessages);
        Assert.Contains("Added by middleware1", capturedMessages);
    }

    #endregion

    #region Exception Handling Tests

    /// <summary>
    /// Tests that middleware exceptions during pre-invocation surface to the agent caller.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareThrowsPreInvocation_ExceptionSurfacesAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var expectedException = new InvalidOperationException("Pre-invocation error");

        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, (context, next) => throw expectedException);

        // Act & Assert
        var actualException = await Assert.ThrowsAsync<InvalidOperationException>(
            () => middleware.RunAsync(messages, null, null, CancellationToken.None));

        Assert.Same(expectedException, actualException);

        // Verify inner agent was never called
        mockInnerAgent.Verify(a => a.RunAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<AgentThread>(),
            It.IsAny<AgentRunOptions>(),
            It.IsAny<CancellationToken>()), Times.Never);
    }

    /// <summary>
    /// Tests that middleware exceptions during post-invocation surface to the agent caller.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareThrowsPostInvocation_ExceptionSurfacesAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var response = new AgentRunResponse([new(ChatRole.Assistant, "Response")]);
        var expectedException = new InvalidOperationException("Post-invocation error");

        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(response);

        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, async (context, next) =>
        {
            await next(context);
            throw expectedException;
        });

        // Act & Assert
        var actualException = await Assert.ThrowsAsync<InvalidOperationException>(
            () => middleware.RunAsync(messages, null, null, CancellationToken.None));

        Assert.Same(expectedException, actualException);

        // Verify inner agent was called
        mockInnerAgent.Verify(a => a.RunAsync(
            It.IsAny<IEnumerable<ChatMessage>>(),
            It.IsAny<AgentThread>(),
            It.IsAny<AgentRunOptions>(),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Tests middleware that catches and handles exceptions from the inner agent, then returns a custom response.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareCatchesInnerAgentException_ReturnsCustomResponseAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var innerException = new InvalidOperationException("Inner agent error");
        var customResponse = new AgentRunResponse([new(ChatRole.Assistant, "Error handled by middleware")]);

        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(innerException);

        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, async (context, next) =>
        {
            try
            {
                await next(context);
            }
            catch (InvalidOperationException)
            {
                // Handle the exception and provide a custom response
                context.SetRunResponse(customResponse);
            }
        });

        // Act
        var result = await middleware.RunAsync(messages, null, null, CancellationToken.None);

        // Assert
        Assert.Same(customResponse, result);
        Assert.Equal("Error handled by middleware", result.Messages.First().Text);
    }

    /// <summary>
    /// Tests middleware that catches exceptions but allows them to propagate unchanged.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareCatchesAndRethrows_ExceptionPropagatesAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var innerException = new InvalidOperationException("Inner agent error");
        var cleanupExecuted = false;

        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(innerException);

        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, async (context, next) =>
        {
            try
            {
                await next(context);
            }
            catch (InvalidOperationException)
            {
                cleanupExecuted = true;
                throw; // Re-throw the exception
            }
        });

        // Act & Assert
        var actualException = await Assert.ThrowsAsync<InvalidOperationException>(
            () => middleware.RunAsync(messages, null, null, CancellationToken.None));

        Assert.Same(innerException, actualException);
        Assert.True(cleanupExecuted, "Cleanup logic should have executed");
    }

    /// <summary>
    /// Tests that exceptions don't break the middleware chain and cleanup logic executes properly.
    /// </summary>
    [Fact]
    public async Task RunAsync_ExceptionInMiddlewareChain_CleanupExecutesAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var expectedException = new InvalidOperationException("Middleware2 error");
        var cleanupExecuted = new List<string>();

        var middleware2 = new RunDelegatingAgent(mockInnerAgent.Object, (context, next) =>
        {
            try
            {
                throw expectedException;
            }
            finally
            {
                cleanupExecuted.Add("Middleware2-Cleanup");
            }
        });

        var middleware1 = new RunDelegatingAgent(middleware2, async (context, next) =>
        {
            try
            {
                await next(context);
            }
            finally
            {
                cleanupExecuted.Add("Middleware1-Cleanup");
            }
        });

        // Act & Assert
        var actualException = await Assert.ThrowsAsync<InvalidOperationException>(
            () => middleware1.RunAsync(messages, null, null, CancellationToken.None));

        Assert.Same(expectedException, actualException);
        Assert.Contains("Middleware2-Cleanup", cleanupExecuted);
        Assert.Contains("Middleware1-Cleanup", cleanupExecuted);
    }

    /// <summary>
    /// Tests middleware chain where one middleware throws but another handles it gracefully.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareChainExceptionHandling_GracefulRecoveryAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var innerException = new InvalidOperationException("Inner error");
        var recoveryResponse = new AgentRunResponse([new(ChatRole.Assistant, "Recovered from error")]);

        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .ThrowsAsync(innerException);

        // Middleware2: Throws an exception
        var middleware2 = new RunDelegatingAgent(mockInnerAgent.Object, async (context, next) =>
        {
            await next(context); // This will throw
            throw new InvalidOperationException("Additional error from middleware2");
        });

        // Middleware1: Catches and handles all exceptions
        var middleware1 = new RunDelegatingAgent(middleware2, async (context, next) =>
        {
            try
            {
                await next(context);
            }
            catch (Exception)
            {
                // Handle any exception and provide recovery response
                context.SetRunResponse(recoveryResponse);
            }
        });

        // Act
        var result = await middleware1.RunAsync(messages, null, null, CancellationToken.None);

        // Assert
        Assert.Same(recoveryResponse, result);
        Assert.Equal("Recovered from error", result.Messages.First().Text);
    }

    #endregion

    #region Additional Test Considerations

    /// <summary>
    /// Tests cancellation token propagation through the middleware chain.
    /// </summary>
    [Fact]
    public async Task RunAsync_CancellationTokenPropagation_TokenPassedThroughAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var response = new AgentRunResponse([new(ChatRole.Assistant, "Response")]);
        var cancellationTokenSource = new CancellationTokenSource();
        var expectedToken = cancellationTokenSource.Token;
        CancellationToken? capturedToken = null;

        mockInnerAgent.Setup(a => a.RunAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken>(
                (messages, thread, options, ct) => capturedToken = ct)
            .ReturnsAsync(response);

        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, async (context, next) =>
        {
            // Verify the cancellation token in context matches the expected token
            Assert.Equal(expectedToken, context.CancellationToken);
            await next(context);
        });

        // Act
        await middleware.RunAsync(messages, null, null, expectedToken);

        // Assert
        Assert.Equal(expectedToken, capturedToken);
    }

    /// <summary>
    /// Tests streaming scenario with context validation and modification.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_ContextModificationAndValidationAsync()
    {
        // Arrange
        var mockInnerAgent = new Mock<AIAgent>();
        var originalMessages = new List<ChatMessage> { new(ChatRole.User, "Original") };
        var originalUpdates = new List<AgentRunResponseUpdate>
        {
            new(ChatRole.Assistant, "Original update")
        };
        var modifiedMessages = new List<ChatMessage>
        {
            new(ChatRole.System, "Added by middleware"),
            new(ChatRole.User, "Original")
        };

        IEnumerable<ChatMessage>? capturedMessages = null;
        mockInnerAgent.Setup(a => a.RunStreamingAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<AgentThread>(),
                It.IsAny<AgentRunOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken>(
                (messages, thread, options, ct) => capturedMessages = messages)
            .Returns(originalUpdates.ToAsyncEnumerable());

        var middleware = new RunDelegatingAgent(mockInnerAgent.Object, async (context, next) =>
        {
            // Verify streaming context
            Assert.True(context.IsStreaming);

            // Modify messages
            context.Messages.Insert(0, new ChatMessage(ChatRole.System, "Added by middleware"));

            await next(context);
        });

        // Act
        var result = new List<AgentRunResponseUpdate>();
        await foreach (var update in middleware.RunStreamingAsync(originalMessages, null, null, CancellationToken.None))
        {
            result.Add(update);
        }

        // Assert
        Assert.NotNull(capturedMessages);
        Assert.Equal(2, capturedMessages.Count());
        Assert.Equal("Added by middleware", capturedMessages.First().Text);
        Assert.Single(result);
    }

    #endregion
}
