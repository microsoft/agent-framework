// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for FunctionCallMiddlewareAgent functionality.
/// </summary>
public sealed class FunctionInvocationDelegatingAgentTests
{
    #region Basic Functionality Tests

    /// <summary>
    /// Tests that FunctionCallMiddlewareAgent can be created with valid parameters.
    /// </summary>
    [Fact]
    public void Constructor_ValidParameters_CreatesInstance()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        static ValueTask<object?> CallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
            => next(context, cancellationToken);

        // Act
        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, CallbackAsync);

        // Assert
        Assert.NotNull(middleware);
        Assert.Equal(innerAgent.Id, middleware.Id);
        Assert.Equal(innerAgent.Name, middleware.Name);
        Assert.Equal(innerAgent.Description, middleware.Description);
    }

    /// <summary>
    /// Tests that constructor throws ArgumentNullException for null inner agent.
    /// </summary>
    [Fact]
    public void Constructor_NullInnerAgent_ThrowsArgumentNullException()
    {
        // Arrange
        static ValueTask<object?> CallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
            => next(context, cancellationToken);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new FunctionInvocationDelegatingAgent(null!, CallbackAsync));
    }
    #endregion

    #region Function Invocation Tests

    /// <summary>
    /// Tests that middleware is invoked when functions are called during agent execution without options.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithFunctionCall_NoOptions_InvokesMiddlewareAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var testFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Function-Executed");
            return "Function result";
        }, "TestFunction", "A test function");

        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object, tools: [testFunction]);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("Middleware-Pre");
            var result = await next(context, cancellationToken);
            executionOrder.Add("Middleware-Post");
            return result;
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        await middleware.RunAsync(messages, null, null, CancellationToken.None);

        // Assert
        Assert.Contains("Middleware-Pre", executionOrder);
        Assert.Contains("Function-Executed", executionOrder);
        Assert.Contains("Middleware-Post", executionOrder);

        // Verify execution order
        var middlewarePreIndex = executionOrder.IndexOf("Middleware-Pre");
        var functionIndex = executionOrder.IndexOf("Function-Executed");
        var middlewarePostIndex = executionOrder.IndexOf("Middleware-Post");

        Assert.True(middlewarePreIndex < functionIndex);
        Assert.True(functionIndex < middlewarePostIndex);
    }

    /// <summary>
    /// Tests that middleware is invoked when functions are called during agent execution without options.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithFunctionCall_AgentRunOptions_InvokesMiddlewareAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var testFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Function-Executed");
            return "Function result";
        }, "TestFunction", "A test function");

        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object, tools: [testFunction]);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("Middleware-Pre");
            var result = await next(context, cancellationToken);
            executionOrder.Add("Middleware-Post");
            return result;
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        await middleware.RunAsync(messages, null, new AgentRunOptions(), CancellationToken.None);

        // Assert
        Assert.Contains("Middleware-Pre", executionOrder);
        Assert.Contains("Function-Executed", executionOrder);
        Assert.Contains("Middleware-Post", executionOrder);

        // Verify execution order
        var middlewarePreIndex = executionOrder.IndexOf("Middleware-Pre");
        var functionIndex = executionOrder.IndexOf("Function-Executed");
        var middlewarePostIndex = executionOrder.IndexOf("Middleware-Post");

        Assert.True(middlewarePreIndex < functionIndex);
        Assert.True(functionIndex < middlewarePostIndex);
    }

    /// <summary>
    /// Tests that middleware is invoked when functions are called during agent execution without options.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithFunctionCall_CustomAgentRunOptions_ThrowsNotSupportedAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var testFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Function-Executed");
            return "Function result";
        }, "TestFunction", "A test function");

        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object, tools: [testFunction]);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("Middleware-Pre");
            var result = await next(context, cancellationToken);
            executionOrder.Add("Middleware-Post");
            return result;
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        await Assert.ThrowsAsync<NotSupportedException>(() =>
            middleware.RunAsync(messages, null, new CustomAgentRunOptions(), CancellationToken.None));
    }

    /// <summary>
    /// Tests that middleware is invoked when functions are called during agent execution.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithFunctionCall_InvokesMiddlewareAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var testFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Function-Executed");
            return "Function result";
        }, "TestFunction", "A test function");

        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("Middleware-Pre");
            var result = await next(context, cancellationToken);
            executionOrder.Add("Middleware-Post");
            return result;
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        await middleware.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.Contains("Middleware-Pre", executionOrder);
        Assert.Contains("Function-Executed", executionOrder);
        Assert.Contains("Middleware-Post", executionOrder);

        // Verify execution order
        var middlewarePreIndex = executionOrder.IndexOf("Middleware-Pre");
        var functionIndex = executionOrder.IndexOf("Function-Executed");
        var middlewarePostIndex = executionOrder.IndexOf("Middleware-Post");

        Assert.True(middlewarePreIndex < functionIndex);
        Assert.True(functionIndex < middlewarePostIndex);
    }

    /// <summary>
    /// Tests that multiple function calls trigger middleware for each invocation.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithMultipleFunctionCalls_InvokesMiddlewareForEachAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var function1 = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Function1-Executed");
            return "Function1 result";
        }, "Function1", "First test function");

        var function2 = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Function2-Executed");
            return "Function2 result";
        }, "Function2", "Second test function");

        var functionCall1 = new FunctionCallContent("call_1", "Function1", new Dictionary<string, object?>());
        var functionCall2 = new FunctionCallContent("call_2", "Function2", new Dictionary<string, object?>());

        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall1, functionCall2);
        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add($"Middleware-Pre-{context.Function.Name}");
            var result = await next(context, cancellationToken);
            executionOrder.Add($"Middleware-Post-{context.Function.Name}");
            return result;
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [function1, function2] });
        await middleware.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.Contains("Middleware-Pre-Function1", executionOrder);
        Assert.Contains("Function1-Executed", executionOrder);
        Assert.Contains("Middleware-Post-Function1", executionOrder);
        Assert.Contains("Middleware-Pre-Function2", executionOrder);
        Assert.Contains("Function2-Executed", executionOrder);
        Assert.Contains("Middleware-Post-Function2", executionOrder);
    }

    #endregion

    #region Context Validation Tests

    /// <summary>
    /// Tests that FunctionInvocationContext contains correct values during middleware execution.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareContext_ContainsCorrectValuesAsync()
    {
        // Arrange
        var testFunction = AIFunctionFactory.Create(() => "Function result", "TestFunction", "A test function");
        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?> { ["param"] = "value" });
        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        FunctionInvocationContext? capturedContext = null;
        AIAgent? capturedAgent = null;

        async ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            capturedContext = context;
            capturedAgent = agent;
            return await next(context, cancellationToken);
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        await middleware.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Equal("TestFunction", capturedContext.Function.Name);
        Assert.Same(innerAgent, capturedAgent); // The agent passed should be the inner agent
        Assert.NotNull(capturedContext.Arguments);
        // Note: Additional context properties would need to be verified based on actual FunctionInvocationContext structure
    }

    #endregion

    #region AIAgentBuilder Use Method Tests

    /// <summary>
    /// Verify that AIAgentBuilder.Use method works correctly with function invocation middleware.
    /// </summary>
    [Fact]
    public async Task AIAgentBuilder_Use_FunctionInvocationMiddleware_WorksCorrectlyAsync()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var testFunction = AIFunctionFactory.Create(() => "test result", name: "TestFunction");
        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var executionOrder = new List<string>();

        // Mock the chat client to return a function call, then a response
        mockChatClient.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, [functionCall])));

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        // Act
        var agent = new AIAgentBuilder(innerAgent)
            .Use((agent, context, next, cancellationToken) =>
            {
                executionOrder.Add("Middleware-Pre");
                var result = next(context, cancellationToken);
                executionOrder.Add("Middleware-Post");
                return result;
            })
            .Build();

        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        await agent.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.Contains("Middleware-Pre", executionOrder);
        Assert.Contains("Middleware-Post", executionOrder);
    }

    /// <summary>
    /// Verify that multiple function invocation middleware are executed.
    /// </summary>
    [Fact]
    public async Task AIAgentBuilder_Use_MultipleFunctionMiddleware_BothExecuteAsync()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var testFunction = AIFunctionFactory.Create(() => "test result", name: "TestFunction");
        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var firstMiddlewareExecuted = false;
        var secondMiddlewareExecuted = false;

        // Mock the chat client to return a function call, then a response
        mockChatClient.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, [functionCall])));

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        // Act
        var agent = new AIAgentBuilder(innerAgent)
            .Use((agent, context, next, cancellationToken) =>
            {
                firstMiddlewareExecuted = true;
                return next(context, cancellationToken);
            })
            .Use((agent, context, next, cancellationToken) =>
            {
                secondMiddlewareExecuted = true;
                return next(context, cancellationToken);
            })
            .Build();

        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        await agent.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.True(firstMiddlewareExecuted, "First middleware should have executed");
        Assert.True(secondMiddlewareExecuted, "Second middleware should have executed");
    }

    /// <summary>
    /// Verify that AIAgentBuilder.Use method throws InvalidOperationException when inner agent is doesn't use a FunctinInvocking.
    /// </summary>
    [Fact]
    public void AIAgentBuilder_Use_NonFICCEnabledAgent_ThrowsInvalidOperationException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();

        // Act & Assert
        var builder = new AIAgentBuilder(mockAgent.Object);
        var exception = Assert.Throws<InvalidOperationException>(() =>
        {
            builder.Use((agent, context, next, cancellationToken) => next(context, cancellationToken));
            builder.Build();
        });
    }

    /// <summary>
    /// Verify that AIAgentBuilder.Use method throws InvalidOperationException when inner agent is doesn't use a FunctinInvokingChatClient.
    /// </summary>
    [Fact]
    public void AIAgentBuilder_Use_NonFICCDecoratedChatClientInAgent_ThrowsInvalidOperationException()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();

        var agent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions() { UseProvidedChatClientAsIs = true });

        // Act & Assert
        var builder = new AIAgentBuilder(agent);
        var exception = Assert.Throws<InvalidOperationException>(() =>
        {
            builder.Use((agent, context, next, cancellationToken) => next(context, cancellationToken));
            builder.Build();
        });
    }

    /// <summary>
    /// Tests function invocation middleware when FunctionInvokingChatClient.CurrentContext is null (direct function invocation).
    /// </summary>
    [Fact]
    public async Task RunAsync_DirectFunctionInvocation_MiddlewareHandlesNullCurrentContextAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var capturedContext = new List<FunctionInvocationContext>();

        var testFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Function-Executed");
            return "Function result";
        }, "TestFunction", "A test function");

        var mockChatClient = new Mock<IChatClient>();

        // Setup mock to directly invoke the function (bypassing FunctionInvokingChatClient)
        mockChatClient.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>(async (messages, options, ct) =>
            {
                // Directly invoke the function to simulate null CurrentContext scenario
                if (options?.Tools?.FirstOrDefault() is AIFunction function)
                {
                    executionOrder.Add("Direct-Function-Invocation");
                    await function.InvokeAsync([], ct);
                }
                return new ChatResponse([new ChatMessage(ChatRole.Assistant, "Response after direct invocation")]);
            });

        var innerAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            UseProvidedChatClientAsIs = true
        });

        async ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("Middleware-Pre");
            capturedContext.Add(context);
            var result = await next(context, cancellationToken);
            executionOrder.Add("Middleware-Post");
            return result;
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        await middleware.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.Contains("Direct-Function-Invocation", executionOrder);
        Assert.Contains("Middleware-Pre", executionOrder);
        Assert.Contains("Function-Executed", executionOrder);
        Assert.Contains("Middleware-Post", executionOrder);

        // Verify that the context was created with Iteration = -1 (indicating no ambient context)
        Assert.Single(capturedContext);
        Assert.Equal(0, capturedContext[0].Iteration);
        Assert.Equal("TestFunction", capturedContext[0].Function.Name);
        Assert.NotNull(capturedContext[0].Arguments);
    }

    #endregion

    #region Error Handling Tests

    /// <summary>
    /// Tests that exceptions thrown by middleware during pre-invocation surface to the caller.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareThrowsPreInvocation_ExceptionSurfacesAsync()
    {
        // Arrange
        var testFunction = AIFunctionFactory.Create(() => "Function result", "TestFunction", "A test function");
        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var expectedException = new InvalidOperationException("Pre-invocation error");

        ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            throw expectedException;
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act & Assert
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        var actualException = await Assert.ThrowsAsync<InvalidOperationException>(
            () => middleware.RunAsync(messages, null, options, CancellationToken.None));

        Assert.Same(expectedException, actualException);
    }

    /// <summary>
    /// Tests that exceptions thrown by the function are handled by middleware.
    /// </summary>
    [Fact]
    public async Task RunAsync_FunctionThrowsException_MiddlewareCanHandleAsync()
    {
        // Arrange
        var functionException = new InvalidOperationException("Function error");
        string ThrowingFunction() => throw functionException;
        var testFunction = AIFunctionFactory.Create(ThrowingFunction, "TestFunction", "A test function");
        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var middlewareHandledException = false;

        async ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            try
            {
                return await next(context, cancellationToken);
            }
            catch (InvalidOperationException)
            {
                middlewareHandledException = true;
                return "Error handled by middleware";
            }
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        await middleware.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.True(middlewareHandledException);
    }

    #endregion

    #region Result Modification Tests

    /// <summary>
    /// Tests that middleware can modify function results.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareModifiesResult_ModifiedResultUsedAsync()
    {
        // Arrange
        var testFunction = AIFunctionFactory.Create(() => "Original result", "TestFunction", "A test function");
        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        const string ModifiedResult = "Modified by middleware";

        static async ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            await next(context, cancellationToken);
            return ModifiedResult; // Return the modified result instead of setting context property
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        var response = await middleware.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.NotNull(response);
        // The modified result should be reflected in the response messages
        var functionResultContent = response.Messages
            .SelectMany(m => m.Contents)
            .OfType<FunctionResultContent>()
            .FirstOrDefault();

        Assert.NotNull(functionResultContent);
        Assert.Equal(ModifiedResult, functionResultContent.Result);
    }

    #endregion

    #region Middleware Chaining Tests

    /// <summary>
    /// Tests execution order with multiple function middleware instances in a chain.
    /// </summary>
    [Fact]
    public async Task RunAsync_MultipleFunctionMiddleware_ExecutesInCorrectOrderAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var testFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Function-Executed");
            return "Function result";
        }, "TestFunction", "A test function");

        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var mockChatClient = new Mock<IChatClient>();

        // Setup sequence: first call returns function call, subsequent calls return final response
        var responseWithFunctionCall = new ChatResponse([
            new ChatMessage(ChatRole.Assistant, [functionCall])
        ]);
        var finalResponse = new ChatResponse([
            new ChatMessage(ChatRole.Assistant, "Final response")
        ]);

        mockChatClient.SetupSequence(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(responseWithFunctionCall)
            .ReturnsAsync(finalResponse);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async ValueTask<object?> FirstMiddlewareAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("First-Pre");
            var result = await next(context, cancellationToken);
            executionOrder.Add("First-Post");
            return result;
        }

        async ValueTask<object?> SecondMiddlewareAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("Second-Pre");
            var result = await next(context, cancellationToken);
            executionOrder.Add("Second-Post");
            return result;
        }

        // Create nested middleware chain
        var firstMiddleware = new FunctionInvocationDelegatingAgent(innerAgent, FirstMiddlewareAsync);
        var secondMiddleware = new FunctionInvocationDelegatingAgent(firstMiddleware, SecondMiddlewareAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        await secondMiddleware.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        var expectedOrder = new[] { "First-Pre", "Second-Pre", "Function-Executed", "Second-Post", "First-Post" };
        Assert.Equal(expectedOrder, executionOrder);
    }

    /// <summary>
    /// Tests that function middleware works correctly when combined with running middleware.
    /// </summary>
    [Fact]
    public async Task RunAsync_FunctionMiddlewareWithRunningMiddleware_BothExecuteAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var testFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Function-Executed");
            return "Function result";
        }, "TestFunction", "A test function");

        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async Task<AgentResponse> RunningMiddlewareCallbackAsync(IEnumerable<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
        {
            executionOrder.Add("Running-Pre");
            var result = await innerAgent.RunAsync(messages, thread, options, cancellationToken);
            executionOrder.Add("Running-Post");
            return result;
        }

        async ValueTask<object?> FunctionMiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("Function-Pre");
            var result = await next(context, cancellationToken);
            executionOrder.Add("Function-Post");
            return result;
        }

        // Create middleware chain: Function -> Running -> Inner using AIAgentBuilder
        var runningMiddleware = new AIAgentBuilder(innerAgent)
            .Use(RunningMiddlewareCallbackAsync, null)
            .Build();
        var functionMiddleware = new FunctionInvocationDelegatingAgent(runningMiddleware, FunctionMiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        await functionMiddleware.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.Contains("Running-Pre", executionOrder);
        Assert.Contains("Running-Post", executionOrder);
        Assert.Contains("Function-Pre", executionOrder);
        Assert.Contains("Function-Post", executionOrder);
        Assert.Contains("Function-Executed", executionOrder);
    }

    #endregion

    #region Streaming Tests

    /// <summary>
    /// Tests that function middleware works correctly with streaming responses.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_WithFunctionCall_InvokesMiddlewareAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var testFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Function-Executed");
            return "Function result";
        }, "TestFunction", "A test function");

        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall);

        // Setup streaming response with function calls
        var streamingResponse = new ChatResponseUpdate[]
        {
            new() { Contents = [functionCall] }, // Include function call in streaming response
            new() { Contents = [new TextContent("Streaming response")] }
        };

        mockChatClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns(streamingResponse.ToAsyncEnumerable());

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("Middleware-Pre");
            var result = await next(context, cancellationToken);
            executionOrder.Add("Middleware-Post");
            return result;
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        var responseUpdates = new List<AgentResponseUpdate>();
        await foreach (var update in middleware.RunStreamingAsync(messages, null, options, CancellationToken.None))
        {
            responseUpdates.Add(update);
        }

        // Assert
        Assert.NotEmpty(responseUpdates);
        Assert.Contains("Middleware-Pre", executionOrder);
        Assert.Contains("Function-Executed", executionOrder);
        Assert.Contains("Middleware-Post", executionOrder);
    }

    #endregion

    #region Edge Cases

    /// <summary>
    /// Tests that middleware is not invoked when no function calls are made.
    /// </summary>
    [Fact]
    public async Task RunAsync_NoFunctionCalls_MiddlewareNotInvokedAsync()
    {
        // Arrange
        var middlewareInvoked = false;
        var mockChatClient = CreateMockChatClient(
            new ChatResponse([new ChatMessage(ChatRole.Assistant, "Regular response")]));

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            middlewareInvoked = true;
            return await next(context, cancellationToken);
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        await middleware.RunAsync(messages, null, null, CancellationToken.None);

        // Assert
        Assert.False(middlewareInvoked);
    }

    /// <summary>
    /// Tests that middleware handles cancellation tokens correctly.
    /// </summary>
    [Fact]
    public async Task RunAsync_CancellationToken_PropagatedToMiddlewareAsync()
    {
        // Arrange
        var testFunction = AIFunctionFactory.Create(() => "Function result", "TestFunction", "A test function");
        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var cancellationTokenSource = new CancellationTokenSource();
        var expectedToken = cancellationTokenSource.Token;
        CancellationToken? capturedToken = null;

        async ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            capturedToken = cancellationToken;
            return await next(context, cancellationToken);
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        await middleware.RunAsync(messages, null, options, expectedToken);

        // Assert
        Assert.Equal(expectedToken, capturedToken);
    }

    /// <summary>
    /// Tests that middleware can prevent function execution by not calling next().
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareDoesNotCallNext_FunctionNotExecutedAsync()
    {
        // Arrange
        var functionExecuted = false;
        var testFunction = AIFunctionFactory.Create(() =>
        {
            functionExecuted = true;
            return "Function result";
        }, "TestFunction", "A test function");

        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>());
        var mockChatClient = CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        static ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            // Don't call next() - this should prevent function execution
            // Return the blocked result directly
            return new ValueTask<object?>("Blocked by middleware");
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        var response = await middleware.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.False(functionExecuted);
        Assert.NotNull(response);

        // Verify the middleware result is used
        var functionResultContent = response.Messages
            .SelectMany(m => m.Contents)
            .OfType<FunctionResultContent>()
            .FirstOrDefault();

        Assert.NotNull(functionResultContent);
        Assert.Equal("Blocked by middleware", functionResultContent.Result);
    }

    #endregion

    /// <summary>
    /// Creates a mock IChatClient with predefined responses for testing.
    /// </summary>
    /// <param name="responses">The responses to return in sequence.</param>
    /// <returns>A configured mock IChatClient.</returns>
    private static Mock<IChatClient> CreateMockChatClient(params ChatResponse[] responses)
    {
        var mockChatClient = new Mock<IChatClient>();
        var responseQueue = new Queue<ChatResponse>(responses);

        mockChatClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(() => responseQueue.Count > 0 ? responseQueue.Dequeue() : responses.LastOrDefault() ?? CreateDefaultResponse());

        return mockChatClient;
    }

    /// <summary>
    /// Creates a mock IChatClient that returns responses with function calls for testing function middleware.
    /// </summary>
    /// <param name="functionCalls">The function calls to include in responses.</param>
    /// <returns>A configured mock IChatClient.</returns>
    private static Mock<IChatClient> CreateMockChatClientWithFunctionCalls(params FunctionCallContent[] functionCalls)
    {
        var mockChatClient = new Mock<IChatClient>();

        var responseWithFunctionCalls = new ChatResponse([
            new ChatMessage(ChatRole.Assistant, functionCalls.Cast<AIContent>().ToList())
        ]);

        mockChatClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(responseWithFunctionCalls);

        return mockChatClient;
    }

    /// <summary>
    /// Creates a default ChatResponse for fallback scenarios.
    /// </summary>
    /// <returns>A default ChatResponse.</returns>
    private static ChatResponse CreateDefaultResponse()
    {
        return new ChatResponse([new ChatMessage(ChatRole.Assistant, "Default response")]);
    }

    /// <summary>
    /// Custom AgentRunOptions class for testing
    /// </summary>
    private sealed class CustomAgentRunOptions : AgentRunOptions;
}
