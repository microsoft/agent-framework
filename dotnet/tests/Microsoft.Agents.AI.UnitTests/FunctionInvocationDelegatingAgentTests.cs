// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

#pragma warning disable Moq1206

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

    [Theory]
    [InlineData(false, "Add")]
    [InlineData(true, "Add")]
    [InlineData(false, "Insert")]
    [InlineData(true, "Insert")]
    [InlineData(false, "Set")]
    [InlineData(true, "Set")]
    [InlineData(false, "Replace")]
    [InlineData(true, "Replace")]
    public async Task RunAsync_DynamicallyAddedFunction_InvokesMiddlewareAsync(bool streaming, string operation)
    {
        // Arrange
        var invokedFunctions = new List<string>();
        var functionExecuted = false;
        var dynamicFunction = AIFunctionFactory.Create(() =>
        {
            functionExecuted = true;
            return "Function result";
        }, "DynamicFunction");
        var loader = AIFunctionFactory.Create(() =>
        {
            var options = FunctionInvokingChatClient.CurrentContext!.Options!;
            switch (operation)
            {
                case "Add":
                    options.Tools!.Add(dynamicFunction);
                    break;
                case "Insert":
                    options.Tools!.Insert(0, dynamicFunction);
                    break;
                case "Set":
                    options.Tools![0] = dynamicFunction;
                    break;
                case "Replace":
                    options.Tools = [dynamicFunction];
                    break;
                default:
                    throw new ArgumentOutOfRangeException(nameof(operation));
            }

            return "Function added";
        }, "LoadFunction");

        var responses = new Queue<ChatResponse>(
        [
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("load", loader.Name)])),
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("invoke", dynamicFunction.Name)])),
            new(new ChatMessage(ChatRole.Assistant, "Complete")),
        ]);
        var mockChatClient = CreateMockChatClient(responses);
        var agent = new ChatClientAgent(mockChatClient.Object, tools: [loader])
            .AsBuilder()
            .Use((agent, context, next, cancellationToken) =>
            {
                invokedFunctions.Add(context.Function.Name);
                return context.Function.Name == dynamicFunction.Name
                    ? new ValueTask<object?>("Function handled by middleware")
                    : next(context, cancellationToken);
            })
            .Build();

        // Act
        var response = streaming
            ? await agent.RunStreamingAsync("Run the functions").ToAgentResponseAsync()
            : await agent.RunAsync("Run the functions");

        // Assert
        Assert.Equal([loader.Name, dynamicFunction.Name], invokedFunctions);
        Assert.False(functionExecuted);
        Assert.Equal("Function handled by middleware", response.Messages
            .SelectMany(m => m.Contents)
            .OfType<FunctionResultContent>()
            .Single(r => r.CallId == "invoke").Result);
        Assert.Empty(responses);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task RunAsync_DynamicFunction_PreservesInvocationOrderAsync(bool streaming, bool replaceTools)
        => await RunDynamicFunctionPreservingInvocationOrderAsync(streaming, replaceTools, recreateOptions: false);

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task RunAsync_RecreatedOptions_PreservesFunctionMiddlewareAsync(bool streaming, bool replaceTools)
        => await RunDynamicFunctionPreservingInvocationOrderAsync(streaming, replaceTools, recreateOptions: true);

    private static async Task RunDynamicFunctionPreservingInvocationOrderAsync(bool streaming, bool replaceTools, bool recreateOptions)
    {
        // Arrange
        var executionOrder = new List<string>();
        var function = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Function");
            return "Function result";
        }, "TestFunction");
        var loader = AIFunctionFactory.Create(() =>
        {
            var options = FunctionInvokingChatClient.CurrentContext!.Options!;
            if (replaceTools)
            {
                options.Tools = [function];
            }
            else
            {
                options.Tools!.Add(function);
                options.Tools[options.Tools.Count - 1] = options.Tools[options.Tools.Count - 1];
            }

            return "Function added";
        }, "LoadFunction");

        var responses = new Queue<ChatResponse>();
        var mockChatClient = CreateMockChatClient(responses);
        using var functionClient = new TrackingFunctionInvokingChatClient(mockChatClient.Object, executionOrder, function.Name);
        async ValueTask<object?> InvokeAsync(FunctionInvocationContext context, CancellationToken cancellationToken)
        {
            if (context.Function.Name == function.Name)
            {
                executionOrder.Add("Invoker-Pre");
            }

            var result = await context.Function.InvokeAsync(context.Arguments, cancellationToken);
            if (context.Function.Name == function.Name)
            {
                executionOrder.Add("Invoker-Post");
            }

            return result;
        }

        functionClient.FunctionInvoker = InvokeAsync;
        var innerAgent = new ChatClientAgent(functionClient, new ChatClientAgentOptions { UseProvidedChatClientAsIs = true });
        var first = innerAgent.AsBuilder().Use(async (agent, context, next, cancellationToken) =>
        {
            Assert.Same(innerAgent, agent);
            if (recreateOptions)
            {
                Assert.Equal(0.5f, context.Options?.Temperature);
            }

            if (context.Function.Name == function.Name)
            {
                executionOrder.Add("First-Pre");
            }

            var result = await next(context, cancellationToken);
            if (context.Function.Name == function.Name)
            {
                executionOrder.Add("First-Post");
            }

            return result;
        }).Build();
        var nextAgent = recreateOptions
            ? new AnonymousDelegatingAIAgent(
                first,
                (messages, session, options, agent, cancellationToken) =>
                    agent.RunAsync(messages, session, RecreateOptions(options), cancellationToken),
                (messages, session, options, agent, cancellationToken) =>
                    agent.RunStreamingAsync(messages, session, RecreateOptions(options), cancellationToken))
            : first;
        var decorated = nextAgent.AsBuilder().Use(async (agent, context, next, cancellationToken) =>
        {
            Assert.Same(nextAgent, agent);
            if (context.Function.Name == function.Name)
            {
                executionOrder.Add("Second-Pre");
            }

            var result = await next(context, cancellationToken);
            if (context.Function.Name == function.Name)
            {
                executionOrder.Add("Second-Post");
            }

            return result;
        }).Build();

        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [function] });
        var expectedOrder = new[]
        {
            "Override-Pre", "Invoker-Pre", "First-Pre", "Second-Pre",
            "Function", "Second-Post", "First-Post", "Invoker-Post", "Override-Post",
        };

        // Act
        for (int run = 0; run < 3; run++)
        {
            executionOrder.Clear();
            if (run > 0)
            {
                options.ChatOptions!.Tools = [loader];
                responses.Enqueue(new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("load", loader.Name)])));
            }

            responses.Enqueue(new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("invoke", function.Name)])));
            responses.Enqueue(new(new ChatMessage(ChatRole.Assistant, "Complete")));
            var response = streaming
                ? await decorated.RunStreamingAsync("Run the functions", options: options).ToAgentResponseAsync()
                : await decorated.RunAsync("Run the functions", options: options);

            // Assert
            Assert.Equal(expectedOrder, executionOrder);
            Assert.Equal("Function result", Assert.IsType<JsonElement>(response.Messages.SelectMany(m => m.Contents)
                .OfType<FunctionResultContent>().Single(r => r.CallId == "invoke").Result).GetString());
            Assert.Empty(responses);
            Assert.Equal(InvokeAsync, functionClient.FunctionInvoker);
        }

        static ChatClientAgentRunOptions RecreateOptions(AgentRunOptions? options)
        {
            var original = Assert.IsType<ChatClientAgentRunOptions>(options);
            var factory = Assert.IsType<Func<IChatClient, IChatClient>>(original.ChatClientFactory);
            return new ChatClientAgentRunOptions(original.ChatOptions?.Clone())
            {
                ChatClientFactory = client => factory(new ConfigureOptionsChatClient(client, options => options.Temperature = 0.5f)),
            };
        }
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task RunAsync_DynamicFunction_PreservesApprovalAsync(bool streaming, bool approved)
    {
        // Arrange
        var invocationCount = 0;
        var observedFunctions = new List<string>();
        var function = AIFunctionFactory.Create(() =>
        {
            invocationCount++;
            return "Function result";
        }, "TestFunction", "Function requiring approval");
        var approvalFunction = new ApprovalRequiredAIFunction(function);
        var loader = AIFunctionFactory.Create(() =>
        {
            var tools = FunctionInvokingChatClient.CurrentContext!.Options!.Tools!;
            tools.Add(approvalFunction);
            Assert.Equal(function.Name, tools[tools.Count - 1].Name);
            Assert.Same(approvalFunction, tools[tools.Count - 1].GetService<ApprovalRequiredAIFunction>());
            Assert.Equal(function.JsonSchema.GetRawText(), Assert.IsAssignableFrom<AIFunction>(tools[tools.Count - 1]).JsonSchema.GetRawText());
            return "Function added";
        }, "LoadFunction");

        var responses = new Queue<ChatResponse>(
        [
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("load", loader.Name)])),
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("invoke", function.Name)])),
        ]);
        var mockChatClient = CreateMockChatClient(responses);
        var agent = new ChatClientAgent(mockChatClient.Object, tools: [loader]).AsBuilder()
            .Use((agent, context, next, cancellationToken) =>
            {
                observedFunctions.Add(context.Function.Name);
                return next(context, cancellationToken);
            }).Build();
        var session = await agent.CreateSessionAsync();

        // Act
        var response = streaming
            ? await agent.RunStreamingAsync("Run the functions", session).ToAgentResponseAsync()
            : await agent.RunAsync("Run the functions", session);

        // Assert
        var request = Assert.Single(response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>());
        Assert.Equal(0, invocationCount);
        Assert.Equal([loader.Name], observedFunctions);
        Assert.Empty(responses);

        // Act
        responses.Enqueue(new(new ChatMessage(ChatRole.Assistant, "Complete")));
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [approvalFunction] });
        var approvalMessage = new ChatMessage(ChatRole.User, [request.CreateResponse(approved)]);
        var resumedResponse = streaming
            ? await agent.RunStreamingAsync(approvalMessage, session, options).ToAgentResponseAsync()
            : await agent.RunAsync(approvalMessage, session, options);

        // Assert
        Assert.Equal(approved ? 1 : 0, invocationCount);
        Assert.Equal(approved ? [loader.Name, function.Name] : new[] { loader.Name }, observedFunctions);
        Assert.Single(resumedResponse.Messages.SelectMany(m => m.Contents)
            .OfType<FunctionResultContent>(), result => result.CallId == "invoke");
        Assert.Empty(responses);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RunAsync_SharedClientAndOptions_IsolatesFunctionMiddlewareAsync(bool streaming)
    {
        // Arrange
        var loadersEntered = 0;
        var gate = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        using var registration = cancellation.Token.Register(() => gate.TrySetCanceled());
        var function = AIFunctionFactory.Create(() => "Function result", "TestFunction");
        var loader = AIFunctionFactory.Create(async () =>
        {
            if (Interlocked.Increment(ref loadersEntered) == 2)
            {
                gate.TrySetResult(true);
            }

            await gate.Task;
            FunctionInvokingChatClient.CurrentContext!.Options!.Tools!.Add(function);
            return "Function added";
        }, "LoadFunction");
        var mockChatClient = new Mock<IChatClient>();
        ChatResponse GetResponse(IEnumerable<ChatMessage> messages)
        {
            var results = messages.SelectMany(m => m.Contents).OfType<FunctionResultContent>().ToArray();
            if (!results.Any(r => r.CallId == "load"))
            {
                return new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("load", loader.Name)]));
            }

            return results.Any(r => r.CallId == "invoke")
                ? new(new ChatMessage(ChatRole.Assistant, "Complete"))
                : new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("invoke", function.Name)]));
        }

        mockChatClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken ct) => Task.FromResult(GetResponse(messages)));
        mockChatClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken ct) => GetResponse(messages).ToChatResponseUpdates().ToAsyncEnumerable());

        using var client = new FunctionInvokingChatClient(mockChatClient.Object);
        var innerAgent = new ChatClientAgent(client, new ChatClientAgentOptions { UseProvidedChatClientAsIs = true });
        var firstInvocations = new List<string>();
        var secondInvocations = new List<string>();
        var first = innerAgent.AsBuilder().Use((agent, context, next, cancellationToken) =>
        {
            firstInvocations.Add(context.Function.Name);
            return context.Function.Name == function.Name ? new ValueTask<object?>("First") : next(context, cancellationToken);
        }).Build();
        var second = innerAgent.AsBuilder().Use((agent, context, next, cancellationToken) =>
        {
            secondInvocations.Add(context.Function.Name);
            return context.Function.Name == function.Name ? new ValueTask<object?>("Second") : next(context, cancellationToken);
        }).Build();
        Func<IChatClient, IChatClient> factory = static client => client;
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [loader] }) { ChatClientFactory = factory };

        // Act
        Task<AgentResponse> RunAsync(AIAgent agent, AgentRunOptions? runOptions = null) => streaming
            ? agent.RunStreamingAsync("Run the functions", options: runOptions ?? options, cancellationToken: cancellation.Token).ToAgentResponseAsync(cancellation.Token)
            : agent.RunAsync("Run the functions", options: runOptions ?? options, cancellationToken: cancellation.Token);
        var responses = await Task.WhenAll(RunAsync(first), RunAsync(second));

        // Assert
        Assert.Equal([loader.Name, function.Name], firstInvocations);
        Assert.Equal([loader.Name, function.Name], secondInvocations);
        Assert.Equal("First", responses[0].Messages.SelectMany(m => m.Contents)
            .OfType<FunctionResultContent>().Single(r => r.CallId == "invoke").Result);
        Assert.Equal("Second", responses[1].Messages.SelectMany(m => m.Contents)
            .OfType<FunctionResultContent>().Single(r => r.CallId == "invoke").Result);
        Assert.Same(factory, options.ChatClientFactory);
        Assert.Same(loader, Assert.Single(options.ChatOptions!.Tools!));
        Assert.Null(client.FunctionInvoker);

        // Act & Assert
        foreach (var response in new[] { await RunAsync(innerAgent), await RunAsync(innerAgent, options.Clone()) })
        {
            Assert.Equal("Function result", Assert.IsType<JsonElement>(response.Messages.SelectMany(m => m.Contents)
                .OfType<FunctionResultContent>().Single(r => r.CallId == "invoke").Result).GetString());
        }

        Assert.Equal([loader.Name, function.Name], firstInvocations);
        Assert.Equal([loader.Name, function.Name], secondInvocations);
        Assert.Same(factory, options.ChatClientFactory);
        Assert.Same(loader, Assert.Single(options.ChatOptions!.Tools!));
    }

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
            .Returns(GetResponseAsync);

        async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken ct)
        {
            // Directly invoke the function to simulate null CurrentContext scenario
            if (options?.Tools?.FirstOrDefault() is AIFunction function)
            {
                executionOrder.Add("Direct-Function-Invocation");
                await function.InvokeAsync([], ct);
            }

            return new ChatResponse([new ChatMessage(ChatRole.Assistant, "Response after direct invocation")]);
        }

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
        var mockChatClient = new Mock<IChatClient>();

        mockChatClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(() => new ChatResponse([
                new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call_123", "TestFunction", new Dictionary<string, object?>())])
            ]));

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

        async Task<AgentResponse> RunningMiddlewareCallbackAsync(IEnumerable<ChatMessage> messages, AgentSession? session, AgentRunOptions? options, AIAgent innerAgent, CancellationToken cancellationToken)
        {
            executionOrder.Add("Running-Pre");
            var result = await innerAgent.RunAsync(messages, session, options, cancellationToken);
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

    #region Options Preservation Tests

    /// <summary>
    /// Tests that FunctionInvocationDelegatingAgent preserves all original AgentRunOptions properties
    /// when converting base AgentRunOptions to ChatClientAgentRunOptions.
    /// </summary>
    [Fact]
    public async Task RunAsync_WithBaseAgentRunOptions_PreservesAllOriginalOptionsAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        var responseFormat = ChatResponseFormat.Json;
        var additionalProperties = new AdditionalPropertiesDictionary { ["key1"] = "value1" };

        Mock<IChatClient> mockChatClient = new();
        var chatClientAgent = new ChatClientAgent(mockChatClient.Object);

        // Wrap the inner agent in a spy that captures the converted options and returns a dummy response
        var spyAgent = new AnonymousDelegatingAIAgent(
            chatClientAgent,
            runFunc: (messages, session, options, innerAgent, ct) =>
            {
                capturedOptions = options;
                return Task.FromResult(new AgentResponse(new ChatResponse(new ChatMessage(ChatRole.Assistant, "test")) { ResponseId = "test" }));
            },
            runStreamingFunc: null);

        static ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
            => next(context, cancellationToken);

        var middleware = new FunctionInvocationDelegatingAgent(spyAgent, MiddlewareCallbackAsync);

        var originalOptions = new AgentRunOptions
        {
            ResponseFormat = responseFormat,
            AllowBackgroundResponses = true,
            ContinuationToken = ResponseContinuationToken.FromBytes(new byte[] { 1, 2, 3 }),
            AdditionalProperties = additionalProperties,
        };

        // Act
        await middleware.RunAsync([new(ChatRole.User, "Test")], null, originalOptions, CancellationToken.None);

        // Assert - All original properties were preserved on the converted options
        Assert.NotNull(capturedOptions);
        Assert.IsType<ChatClientAgentRunOptions>(capturedOptions);
        Assert.Same(responseFormat, capturedOptions.ResponseFormat);
        Assert.True(capturedOptions.AllowBackgroundResponses);
        Assert.Same(originalOptions.ContinuationToken, capturedOptions.ContinuationToken);
        Assert.Same(additionalProperties, capturedOptions.AdditionalProperties);
    }

    #endregion

    private static Mock<IChatClient> CreateMockChatClient(Queue<ChatResponse> responses)
    {
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(() => responses.Dequeue());
        mockChatClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns(() => responses.Dequeue().ToChatResponseUpdates().ToAsyncEnumerable());
        return mockChatClient;
    }

    private sealed class TrackingFunctionInvokingChatClient(IChatClient innerClient, List<string> executionOrder, string functionName)
        : FunctionInvokingChatClient(innerClient)
    {
        protected override async ValueTask<object?> InvokeFunctionAsync(FunctionInvocationContext context, CancellationToken cancellationToken)
        {
            if (context.Function.Name == functionName)
            {
                executionOrder.Add("Override-Pre");
            }

            var result = await base.InvokeFunctionAsync(context, cancellationToken);
            if (context.Function.Name == functionName)
            {
                executionOrder.Add("Override-Post");
            }

            return result;
        }
    }

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
