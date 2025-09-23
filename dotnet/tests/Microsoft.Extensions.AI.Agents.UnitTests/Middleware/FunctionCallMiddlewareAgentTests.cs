// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests.Middleware;

/// <summary>
/// Unit tests for FunctionCallMiddlewareAgent functionality.
/// </summary>
public sealed class FunctionCallMiddlewareAgentTests
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
        static Task CallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next) => next(context);

        // Act
        var middleware = new FunctionCallMiddlewareAgent(innerAgent, CallbackAsync);

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
        static Task CallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next) => next(context);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new FunctionCallMiddlewareAgent(null!, CallbackAsync));
    }
    #endregion

    #region Function Invocation Tests

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
        var mockChatClient = MiddlewareTestHelpers.CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async Task MiddlewareCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            executionOrder.Add("Middleware-Pre");
            await next(context);
            executionOrder.Add("Middleware-Post");
        }

        var middleware = new FunctionCallMiddlewareAgent(innerAgent, MiddlewareCallbackAsync);

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

        var mockChatClient = MiddlewareTestHelpers.CreateMockChatClientWithFunctionCalls(functionCall1, functionCall2);
        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async Task MiddlewareCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            executionOrder.Add($"Middleware-Pre-{context.Function.Name}");
            await next(context);
            executionOrder.Add($"Middleware-Post-{context.Function.Name}");
        }

        var middleware = new FunctionCallMiddlewareAgent(innerAgent, MiddlewareCallbackAsync);

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
    /// Tests that AgentFunctionInvocationContext contains correct values during middleware execution.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareContext_ContainsCorrectValuesAsync()
    {
        // Arrange
        var testFunction = AIFunctionFactory.Create(() => "Function result", "TestFunction", "A test function");
        var functionCall = new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?> { ["param"] = "value" });
        var mockChatClient = MiddlewareTestHelpers.CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        AgentFunctionInvocationContext? capturedContext = null;

        async Task MiddlewareCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            capturedContext = context;
            await next(context);
        }

        var middleware = new FunctionCallMiddlewareAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        await middleware.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.NotNull(capturedContext);
        Assert.Equal("TestFunction", capturedContext.Function.Name);
        Assert.Equal("call_123", capturedContext.CallContent.CallId);
        Assert.Equal("TestFunction", capturedContext.CallContent.Name);
        Assert.Same(middleware, capturedContext.Agent); // The context agent should be the middleware agent
        Assert.NotNull(capturedContext.Arguments);
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
        var mockChatClient = MiddlewareTestHelpers.CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var expectedException = new InvalidOperationException("Pre-invocation error");

        Task MiddlewareCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            throw expectedException;
        }

        var middleware = new FunctionCallMiddlewareAgent(innerAgent, MiddlewareCallbackAsync);

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
        var mockChatClient = MiddlewareTestHelpers.CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var middlewareHandledException = false;

        async Task MiddlewareCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            try
            {
                await next(context);
            }
            catch (InvalidOperationException)
            {
                middlewareHandledException = true;
                context.FunctionResult = "Error handled by middleware";
            }
        }

        var middleware = new FunctionCallMiddlewareAgent(innerAgent, MiddlewareCallbackAsync);

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
        var mockChatClient = MiddlewareTestHelpers.CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        const string ModifiedResult = "Modified by middleware";

        async Task MiddlewareCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            await next(context);
            context.FunctionResult = ModifiedResult;
        }

        var middleware = new FunctionCallMiddlewareAgent(innerAgent, MiddlewareCallbackAsync);

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

        async Task FirstMiddlewareAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            executionOrder.Add("First-Pre");
            await next(context);
            executionOrder.Add("First-Post");
        }

        async Task SecondMiddlewareAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            executionOrder.Add("Second-Pre");
            await next(context);
            executionOrder.Add("Second-Post");
        }

        // Create nested middleware chain
        var firstMiddleware = new FunctionCallMiddlewareAgent(innerAgent, FirstMiddlewareAsync);
        var secondMiddleware = new FunctionCallMiddlewareAgent(firstMiddleware, SecondMiddlewareAsync);

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
        var mockChatClient = MiddlewareTestHelpers.CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async Task RunningMiddlewareCallbackAsync(AgentRunContext context, Func<AgentRunContext, Task> next)
        {
            executionOrder.Add("Running-Pre");
            await next(context);
            executionOrder.Add("Running-Post");
        }

        async Task FunctionMiddlewareCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            executionOrder.Add("Function-Pre");
            await next(context);
            executionOrder.Add("Function-Post");
        }

        // Create middleware chain: Function -> Running -> Inner
        var runningMiddleware = new RunningMiddlewareAgent(innerAgent, RunningMiddlewareCallbackAsync);
        var functionMiddleware = new FunctionCallMiddlewareAgent(runningMiddleware, FunctionMiddlewareCallbackAsync);

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
        var mockChatClient = MiddlewareTestHelpers.CreateMockChatClientWithFunctionCalls(functionCall);

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

        async Task MiddlewareCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            executionOrder.Add("Middleware-Pre");
            await next(context);
            executionOrder.Add("Middleware-Post");
        }

        var middleware = new FunctionCallMiddlewareAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        var responseUpdates = new List<AgentRunResponseUpdate>();
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

    #region Edge Cases and Integration Tests

    /// <summary>
    /// Tests that middleware is not invoked when no function calls are made.
    /// </summary>
    [Fact]
    public async Task RunAsync_NoFunctionCalls_MiddlewareNotInvokedAsync()
    {
        // Arrange
        var middlewareInvoked = false;
        var mockChatClient = MiddlewareTestHelpers.CreateMockChatClient(
            new ChatResponse([new ChatMessage(ChatRole.Assistant, "Regular response")]));

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async Task MiddlewareCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            middlewareInvoked = true;
            await next(context);
        }

        var middleware = new FunctionCallMiddlewareAgent(innerAgent, MiddlewareCallbackAsync);

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
        var mockChatClient = MiddlewareTestHelpers.CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };
        var cancellationTokenSource = new CancellationTokenSource();
        var expectedToken = cancellationTokenSource.Token;
        CancellationToken? capturedToken = null;

        async Task MiddlewareCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            capturedToken = context.CancellationToken;
            await next(context);
        }

        var middleware = new FunctionCallMiddlewareAgent(innerAgent, MiddlewareCallbackAsync);

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
        var mockChatClient = MiddlewareTestHelpers.CreateMockChatClientWithFunctionCalls(functionCall);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        Task MiddlewareCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            // Don't call next() - this should prevent function execution
            context.FunctionResult = "Blocked by middleware";
            return Task.CompletedTask;
        }

        var middleware = new FunctionCallMiddlewareAgent(innerAgent, MiddlewareCallbackAsync);

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
}
