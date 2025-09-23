// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests.Middleware;

/// <summary>
/// Unit tests for AIAgentBuilderExtensions middleware functionality.
/// </summary>
public sealed class AIAgentBuilderExtensionsTests
{
    #region UseRunningContext Tests

    /// <summary>
    /// Tests that UseRunningContext properly validates null builder parameter.
    /// </summary>
    [Fact]
    public void UseRunningContext_NullBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        AIAgentBuilder? nullBuilder = null;
        static Task callbackAsync(AgentRunContext context, Func<AgentRunContext, Task> next) => next(context);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("builder", () => nullBuilder!.UseRunningContext(callbackAsync));
    }

    /// <summary>
    /// Tests that UseRunningContext properly validates null callback parameter.
    /// </summary>
    [Fact]
    public void UseRunningContext_NullCallback_ThrowsArgumentNullException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        Func<AgentRunContext, Func<AgentRunContext, Task>, Task>? nullCallback = null;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => builder.UseRunningContext(nullCallback!).Build());
    }

    /// <summary>
    /// Tests that UseRunningContext returns the same builder instance for method chaining.
    /// </summary>
    [Fact]
    public void UseRunningContext_ValidParameters_ReturnsSameBuilder()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        static Task callbackAsync(AgentRunContext context, Func<AgentRunContext, Task> next) => next(context);

        // Act
        var result = builder.UseRunningContext(callbackAsync);

        // Assert
        Assert.Same(builder, result);
    }

    /// <summary>
    /// Tests that UseRunningContext properly wraps the agent with RunningMiddlewareAgent.
    /// </summary>
    [Fact]
    public void UseRunningContext_ValidParameters_WrapsWithRunningMiddlewareAgent()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        var callbackExecuted = false;
        Task callbackAsync(AgentRunContext context, Func<AgentRunContext, Task> next)
        {
            callbackExecuted = true;
            return next(context);
        }

        // Act
        var result = builder.UseRunningContext(callbackAsync).Build();

        // Assert
        Assert.IsType<RunningMiddlewareAgent>(result);

        // Verify the callback is properly set by checking if it gets executed
        // This is an indirect test since RunningMiddlewareAgent is internal
        Assert.False(callbackExecuted); // Not executed until agent runs
    }

    #endregion

    #region Use (AgentRunContext) Tests

    /// <summary>
    /// Tests that Use with AgentRunContext properly validates null builder parameter.
    /// </summary>
    [Fact]
    public void Use_AgentRunContext_NullBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        AIAgentBuilder? nullBuilder = null;
        static Task callbackAsync(AgentRunContext context, Func<AgentRunContext, Task> next) => next(context);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("builder", () => nullBuilder!.Use(callbackAsync));
    }

    /// <summary>
    /// Tests that Use with AgentRunContext properly validates null callback parameter.
    /// </summary>
    [Fact]
    public void Use_AgentRunContext_NullCallback_ThrowsArgumentNullException()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        Func<AgentRunContext, Func<AgentRunContext, Task>, Task>? nullCallback = null;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => builder.Use(nullCallback!).Build());
    }

    /// <summary>
    /// Tests that Use with AgentRunContext returns the same builder instance for method chaining.
    /// </summary>
    [Fact]
    public void Use_AgentRunContext_ValidParameters_ReturnsSameBuilder()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        static Task callbackAsync(AgentRunContext context, Func<AgentRunContext, Task> next) => next(context);

        // Act
        var result = builder.Use(callbackAsync);

        // Assert
        Assert.Same(builder, result);
    }

    #endregion

    #region UseFunctionInvocationContext Tests

    /// <summary>
    /// Tests that UseFunctionInvocationContext properly validates null builder parameter.
    /// </summary>
    [Fact]
    public void UseFunctionInvocationContext_NullBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        AIAgentBuilder? nullBuilder = null;
        static Task callbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next) => next(context);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("builder", () => nullBuilder!.UseFunctionInvocationContext(callbackAsync));
    }

    /// <summary>
    /// Tests that UseFunctionInvocationContext properly validates null callback parameter.
    /// </summary>
    [Fact]
    public void UseFunctionInvocationContext_NullCallback_ThrowsArgumentNullException()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var chatClientAgent = new ChatClientAgent(mockChatClient.Object);
        var builder = new AIAgentBuilder(chatClientAgent);
        Func<AgentFunctionInvocationContext, Func<AgentFunctionInvocationContext, Task>, Task>? nullCallback = null;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => builder.UseFunctionInvocationContext(nullCallback!).Build());
    }

    /// <summary>
    /// Tests that UseFunctionInvocationContext returns the same builder instance for method chaining.
    /// </summary>
    [Fact]
    public void UseFunctionInvocationContext_ValidParameters_ReturnsSameBuilder()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        static Task callbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next) => next(context);

        // Act
        var result = builder.UseFunctionInvocationContext(callbackAsync);

        // Assert
        Assert.Same(builder, result);
    }

    #endregion

    #region Use (AgentFunctionInvocationContext) Tests

    /// <summary>
    /// Tests that Use with AgentFunctionInvocationContext properly validates null builder parameter.
    /// </summary>
    [Fact]
    public void Use_AgentFunctionInvocationContext_NullBuilder_ThrowsArgumentNullException()
    {
        // Arrange
        AIAgentBuilder? nullBuilder = null;
        static Task callbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next) => next(context);

        // Act & Assert
        Assert.Throws<ArgumentNullException>("builder", () => nullBuilder!.Use(callbackAsync));
    }

    /// <summary>
    /// Tests that Use with AgentFunctionInvocationContext properly validates null callback parameter.
    /// </summary>
    [Fact]
    public void Use_AgentFunctionInvocationContext_NullCallback_ThrowsArgumentNullException()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var chatClientAgent = new ChatClientAgent(mockChatClient.Object);
        var builder = new AIAgentBuilder(chatClientAgent);
        Func<AgentFunctionInvocationContext, Func<AgentFunctionInvocationContext, Task>, Task>? nullCallback = null;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => builder.Use(nullCallback!).Build());
    }

    /// <summary>
    /// Tests that Use with AgentFunctionInvocationContext returns the same builder instance for method chaining.
    /// </summary>
    [Fact]
    public void Use_AgentFunctionInvocationContext_ValidParameters_ReturnsSameBuilder()
    {
        // Arrange
        var mockAgent = new Mock<AIAgent>();
        var builder = new AIAgentBuilder(mockAgent.Object);
        static Task callbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next) => next(context);

        // Act
        var result = builder.Use(callbackAsync);

        // Assert
        Assert.Same(builder, result);
    }

    /// <summary>
    /// Tests that Use with AgentFunctionInvocationContext requires ChatClientAgent and throws for other agent types.
    /// </summary>
    [Fact]
    public void Use_AgentFunctionInvocationContext_NonChatClientAgent_ThrowsInvalidOperationException()
    {
        // Arrange - Use a concrete agent that is not a ChatClientAgent
        var nonChatClientAgent = new TestNonChatClientAgent();
        var builder = new AIAgentBuilder(nonChatClientAgent);
        static Task callbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next) => next(context);

        // Act & Assert
        var exception = Assert.Throws<InvalidOperationException>(() => builder.Use(callbackAsync).Build());
        Assert.Contains("FunctionCallMiddlewareAgent", exception.Message);
        Assert.Contains("ChatClientAgent", exception.Message);
    }

    #endregion

    #region Method Chaining Tests

    /// <summary>
    /// Tests that multiple middleware can be chained together using the extension methods.
    /// </summary>
    [Fact]
    public void MiddlewareChaining_MultipleExtensions_ChainsCorrectly()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var chatClientAgent = new ChatClientAgent(mockChatClient.Object);
        var builder = new AIAgentBuilder(chatClientAgent);

        static Task runCallbackAsync(AgentRunContext context, Func<AgentRunContext, Task> next) => next(context);
        static Task funcCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next) => next(context);

        // Create explicit delegate types to ensure correct overload resolution
        Func<AgentRunContext, Func<AgentRunContext, Task>, Task> runDelegate = runCallbackAsync;
        Func<AgentFunctionInvocationContext, Func<AgentFunctionInvocationContext, Task>, Task> funcDelegate = funcCallbackAsync;

        // Act - Test just the function middleware to see if it works
        // Let's debug by checking what type funcDelegate actually is
        Console.WriteLine($"funcDelegate type: {funcDelegate.GetType()}");
        Console.WriteLine($"runDelegate type: {runDelegate.GetType()}");

        // Test if ChatClientAgent is detected properly
        Console.WriteLine($"ChatClientAgent service: {chatClientAgent.GetService<ChatClientAgent>()}");

        var result = builder
            .UseFunctionInvocationContext(funcCallbackAsync)
            .UseRunningContext(runCallbackAsync)
            .Build();

        // Assert
        Assert.NotNull(result);
        // The outermost agent should be a FunctionCallMiddlewareAgent (function middleware added)
        Console.WriteLine($"Result type: {result.GetType().Name}");
        Assert.IsType<FunctionCallMiddlewareAgent>(result);

        // Verify the middleware chain structure by checking inner agents
        var functionMiddleware = (FunctionCallMiddlewareAgent)result;
        var innerAgent = GetInnerAgent(functionMiddleware);
        Assert.IsType<RunningMiddlewareAgent>(innerAgent); // Should be the second RunningMiddleware

        var runningMiddleware = (RunningMiddlewareAgent)innerAgent;
        var coreAgent = GetInnerAgent(runningMiddleware);
        Assert.IsType<ChatClientAgent>(coreAgent); // Should be the first RunningMiddleware
    }

    /// <summary>
    /// Helper method to get the inner agent using reflection.
    /// </summary>
    private static AIAgent GetInnerAgent(AIAgent agent)
    {
        var innerAgentProperty = agent.GetType().GetProperty("InnerAgent", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        if (innerAgentProperty != null)
        {
            return (AIAgent)innerAgentProperty.GetValue(agent)!;
        }

        // Try field if property doesn't exist
        var innerAgentField = agent.GetType().GetField("InnerAgent", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
        if (innerAgentField != null)
        {
            return (AIAgent)innerAgentField.GetValue(agent)!;
        }

        throw new InvalidOperationException($"Could not find InnerAgent property or field on {agent.GetType().Name}");
    }

    /// <summary>
    /// Tests that function invocation middleware creates FunctionCallMiddlewareAgent when called explicitly.
    /// </summary>
    [Fact]
    public void Use_ExplicitFunctionInvocationDelegate_CreatesFunctionCallMiddlewareAgent()
    {
        // Arrange
        var mockChatClient = new Mock<IChatClient>();
        var chatClientAgent = new ChatClientAgent(mockChatClient.Object);
        var builder = new AIAgentBuilder(chatClientAgent);

        // Use explicit delegate type to force the correct overload
        static Task FuncCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next) => next(context);

        // Act
        var result = builder.Use(FuncCallbackAsync).Build();

        // Assert
        Assert.NotNull(result);
        Assert.IsType<FunctionCallMiddlewareAgent>(result);
    }

    #endregion

    #region Extension Method Working Middleware Tests

    /// <summary>
    /// Tests that Use extension method with AgentFunctionInvocationContext creates working middleware.
    /// </summary>
    [Fact]
    public async Task Use_AgentFunctionInvocationContext_WorkingMiddlewareAsync()
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

        async Task MiddlewareCallbackAsync(AgentFunctionInvocationContext context, Func<AgentFunctionInvocationContext, Task> next)
        {
            executionOrder.Add("Middleware-Pre");
            await next(context);
            executionOrder.Add("Middleware-Post");
        }

        // Act - Use the extension method
        var agent = innerAgent.AsBuilder()
            .Use(MiddlewareCallbackAsync)
            .Build();

        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [testFunction] });
        var response = await agent.RunAsync(messages, null, options, CancellationToken.None);

        // Assert
        Assert.NotNull(response);
        Assert.Contains("Middleware-Pre", executionOrder);
        Assert.Contains("Function-Executed", executionOrder);
        Assert.Contains("Middleware-Post", executionOrder);
        var expectedOrder = new[] { "Middleware-Pre", "Function-Executed", "Middleware-Post" };
        Assert.Equal(expectedOrder, executionOrder);
    }

    /// <summary>
    /// Tests that UseRunningContext extension method creates working middleware.
    /// </summary>
    [Fact]
    public async Task UseRunningContext_WorkingMiddlewareAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var mockChatClient = new Mock<IChatClient>();
        var finalResponse = new ChatResponse([
            new ChatMessage(ChatRole.Assistant, "Final response")
        ]);

        mockChatClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(finalResponse);

        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "Test message") };

        async Task MiddlewareCallbackAsync(AgentRunContext context, Func<AgentRunContext, Task> next)
        {
            executionOrder.Add("Middleware-Pre");
            await next(context);
            executionOrder.Add("Middleware-Post");
        }

        // Act - Use the UseRunningContext extension method
        var agent = innerAgent.AsBuilder()
            .UseRunningContext(MiddlewareCallbackAsync)
            .Build();

        var response = await agent.RunAsync(messages, null, null, CancellationToken.None);

        // Assert
        Assert.NotNull(response);
        Assert.Contains("Middleware-Pre", executionOrder);
        Assert.Contains("Middleware-Post", executionOrder);
        var expectedOrder = new[] { "Middleware-Pre", "Middleware-Post" };
        Assert.Equal(expectedOrder, executionOrder);
    }

    #endregion
}

/// <summary>
/// Test agent that is not a ChatClientAgent, used for testing scenarios where ChatClientAgent is required.
/// </summary>
internal sealed class TestNonChatClientAgent : AIAgent
{
    public override string Id => "test-non-chat-client-agent";

    public override Task<AgentRunResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return Task.FromResult(new AgentRunResponse([new ChatMessage(ChatRole.Assistant, "Test response")]));
    }

    public override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        return AsyncEnumerable.Empty<AgentRunResponseUpdate>();
    }

    public override AgentThread GetNewThread() => new();
}
