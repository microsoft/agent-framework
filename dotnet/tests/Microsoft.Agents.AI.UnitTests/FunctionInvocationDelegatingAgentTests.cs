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
    [InlineData(false, "None", false)]
    [InlineData(true, "None", false)]
    [InlineData(false, "None", true)]
    [InlineData(true, "None", true)]
    [InlineData(false, "RequiredTool", false)]
    [InlineData(true, "RequiredTool", false)]
    [InlineData(false, "RequiredTool", true)]
    [InlineData(true, "RequiredTool", true)]
    [InlineData(false, "ConversationId", false)]
    [InlineData(true, "ConversationId", false)]
    [InlineData(false, "ConversationId", true)]
    [InlineData(true, "ConversationId", true)]
    public async Task RunAsync_InterIterationOptionsClone_PreservesDynamicFunctionMiddlewareAsync(
        bool streaming, string cloneTrigger, bool replaceTools)
        => await VerifyInterIterationOptionsCloneAsync(streaming, cloneTrigger, replaceTools);

    [Theory]
    [InlineData(false, "RequiredTool")]
    [InlineData(true, "RequiredTool")]
    [InlineData(false, "ConversationId")]
    [InlineData(true, "ConversationId")]
    public async Task RunAsync_InterIterationOptionsClone_AllowedFunctionExecutesAsync(bool streaming, string cloneTrigger)
        => await VerifyInterIterationOptionsCloneAsync(streaming, cloneTrigger, replaceTools: true, allowExecution: true);

    [Theory]
    [InlineData(false, "RequiredTool")]
    [InlineData(true, "RequiredTool")]
    [InlineData(false, "ConversationId")]
    [InlineData(true, "ConversationId")]
    public async Task RunAsync_InterIterationOptionsClone_LoaderFailurePreservesMiddlewareAsync(bool streaming, string cloneTrigger)
        => await VerifyInterIterationOptionsCloneAsync(streaming, cloneTrigger, replaceTools: true, loaderThrows: true);

    private static async Task VerifyInterIterationOptionsCloneAsync(
        bool streaming, string cloneTrigger, bool replaceTools, bool allowExecution = false, bool loaderThrows = false)
    {
        // Arrange
        var invocations = new List<string>();
        var invocationCount = 0;
        var loaderFailure = new InvalidOperationException("Loader failed after updating tools");
        ChatOptions? initialOptions = null;
        var function = AIFunctionFactory.Create(() =>
        {
            invocationCount++;
            return "Function result";
        }, "DynamicFunction");
        var secondLoader = AIFunctionFactory.Create(() =>
        {
            var options = FunctionInvokingChatClient.CurrentContext!.Options!;
            if (cloneTrigger == "None")
            {
                Assert.Same(initialOptions, options);
            }
            else
            {
                Assert.NotSame(initialOptions, options);
            }

            if (replaceTools)
            {
                options.Tools = [function];
            }
            else
            {
                options.Tools!.Add(function);
            }

            if (loaderThrows)
            {
                throw loaderFailure;
            }

            return "Function added";
        }, "SecondLoader");
        var firstLoader = AIFunctionFactory.Create(() =>
        {
            initialOptions = FunctionInvokingChatClient.CurrentContext!.Options!;
            initialOptions.Tools!.Add(secondLoader);
            return "Second loader added";
        }, "FirstLoader");
        var conversationId = cloneTrigger == "ConversationId" ? "conversation" : null;
        var responses = new Queue<ChatResponse>(
        [
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("first", firstLoader.Name)])) { ConversationId = conversationId },
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("second", secondLoader.Name)])) { ConversationId = conversationId },
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("invoke", function.Name)])) { ConversationId = conversationId },
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("invoke-again", function.Name)])) { ConversationId = conversationId },
            new(new ChatMessage(ChatRole.Assistant, "Complete")) { ConversationId = conversationId },
        ]);
        using var client = new FunctionInvokingChatClient(CreateMockChatClient(responses).Object)
        {
            MaximumConsecutiveErrorsPerRequest = 1,
        };
        var innerAgent = new ChatClientAgent(client, tools: [firstLoader]);
        var first = innerAgent.AsBuilder().Use(async (agent, context, next, cancellationToken) =>
        {
            invocations.Add($"First-Pre-{context.Function.Name}");
            var result = await next(context, cancellationToken);
            invocations.Add($"First-Post-{context.Function.Name}");
            return result;
        }).Build();
        var decorated = first.AsBuilder().Use(async (agent, context, next, cancellationToken) =>
        {
            invocations.Add($"Second-Pre-{context.Function.Name}");
            var result = context.Function.Name == function.Name && !allowExecution
                ? "Handled by middleware"
                : await next(context, cancellationToken);
            invocations.Add($"Second-Post-{context.Function.Name}");
            return result;
        }).Build();
        var options = new ChatClientAgentRunOptions(new ChatOptions
        {
            ToolMode = cloneTrigger == "RequiredTool" ? ChatToolMode.RequireAny : null,
        });

        // Act
        var response = streaming
            ? await decorated.RunStreamingAsync("Run the functions", options: options).ToAgentResponseAsync()
            : await decorated.RunAsync("Run the functions", options: options);

        // Assert
        Assert.Equal(new[] { firstLoader.Name, secondLoader.Name, function.Name, function.Name }.SelectMany(name =>
            loaderThrows && name == secondLoader.Name
                ? new[] { $"First-Pre-{name}", $"Second-Pre-{name}" }
                : new[] { $"First-Pre-{name}", $"Second-Pre-{name}", $"Second-Post-{name}", $"First-Post-{name}" }), invocations);
        Assert.Equal(allowExecution ? 2 : 0, invocationCount);
        var results = response.Messages.SelectMany(m => m.Contents).OfType<FunctionResultContent>().ToArray();
        foreach (var callId in new[] { "invoke", "invoke-again" })
        {
            var result = Assert.Single(results, result => result.CallId == callId).Result;
            if (allowExecution)
            {
                Assert.Equal("Function result", Assert.IsType<JsonElement>(result).GetString());
            }
            else
            {
                Assert.Equal("Handled by middleware", result);
            }
        }

        Assert.Same(loaderThrows ? loaderFailure : null, Assert.Single(results, result => result.CallId == "second").Exception);
        Assert.Empty(responses);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task RunAsync_InterIterationOptionsClone_PreservesApprovalAsync(bool streaming, bool approved)
    {
        // Arrange
        var invocationCount = 0;
        var middlewareInvocations = new List<string>();
        ChatOptions? initialOptions = null;
        var function = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() =>
        {
            invocationCount++;
            return "Function result";
        }, "DynamicFunction"));
        var secondLoader = AIFunctionFactory.Create(() =>
        {
            var options = FunctionInvokingChatClient.CurrentContext!.Options!;
            Assert.NotSame(initialOptions, options);
            options.Tools!.Add(function);
            return "Function added";
        }, "SecondLoader");
        var firstLoader = AIFunctionFactory.Create(() =>
        {
            initialOptions = FunctionInvokingChatClient.CurrentContext!.Options!;
            initialOptions.Tools!.Add(secondLoader);
            return "Second loader added";
        }, "FirstLoader");
        var responses = new Queue<ChatResponse>(
        [
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("first", firstLoader.Name)])),
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("second", secondLoader.Name)])),
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("invoke", function.Name)])),
        ]);
        var agent = new ChatClientAgent(CreateMockChatClient(responses).Object, tools: [firstLoader]).AsBuilder()
            .Use((agent, context, next, cancellationToken) =>
            {
                middlewareInvocations.Add(context.Function.Name);
                return next(context, cancellationToken);
            }).Build();
        var session = await agent.CreateSessionAsync();
        var runOptions = new ChatClientAgentRunOptions(new ChatOptions { ToolMode = ChatToolMode.RequireAny });

        // Act
        var response = streaming
            ? await agent.RunStreamingAsync("Run the functions", session, runOptions).ToAgentResponseAsync()
            : await agent.RunAsync("Run the functions", session, runOptions);

        // Assert
        var request = Assert.Single(response.Messages.SelectMany(m => m.Contents).OfType<ToolApprovalRequestContent>());
        Assert.Equal(0, invocationCount);
        Assert.Equal([firstLoader.Name, secondLoader.Name], middlewareInvocations);
        Assert.Empty(responses);

        // Act
        responses.Enqueue(new(new ChatMessage(ChatRole.Assistant, "Complete")));
        var approval = new ChatMessage(ChatRole.User, [request.CreateResponse(approved)]);
        var resumedOptions = new ChatClientAgentRunOptions(new ChatOptions { Tools = [function] });
        var resumedResponse = streaming
            ? await agent.RunStreamingAsync(approval, session, resumedOptions).ToAgentResponseAsync()
            : await agent.RunAsync(approval, session, resumedOptions);

        // Assert
        Assert.Equal(approved ? 1 : 0, invocationCount);
        Assert.Equal(approved ? [firstLoader.Name, secondLoader.Name, function.Name] : new[] { firstLoader.Name, secondLoader.Name }, middlewareInvocations);
        Assert.Single(resumedResponse.Messages.SelectMany(m => m.Contents)
            .OfType<FunctionResultContent>(), result => result.CallId == "invoke");
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

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task RunAsync_OpaqueChatClient_PreservesFunctionMiddlewareAsync(bool streaming, bool replaceTools)
        => await RunDynamicFunctionPreservingInvocationOrderAsync(streaming, replaceTools, recreateOptions: true, hideServices: true);

    private static async Task RunDynamicFunctionPreservingInvocationOrderAsync(bool streaming, bool replaceTools, bool recreateOptions, bool hideServices = false)
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

        ChatClientAgentRunOptions RecreateOptions(AgentRunOptions? options)
        {
            var original = Assert.IsType<ChatClientAgentRunOptions>(options);
            var factory = Assert.IsType<Func<IChatClient, IChatClient>>(original.ChatClientFactory);
            return new ChatClientAgentRunOptions(original.ChatOptions?.Clone())
            {
                ChatClientFactory = client =>
                {
                    var pipeline = factory(new ConfigureOptionsChatClient(client, options => options.Temperature = 0.5f));
                    return hideServices ? new OpaqueChatClient(pipeline) : pipeline;
                },
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

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task RunAsync_NestedAgent_IsolatesFunctionMiddlewareAsync(bool streaming, bool nestedStreaming)
    {
        // Arrange
        var innerInvocations = new List<string>();
        var outerInvocations = new List<string>();
        var innerFunction = AIFunctionFactory.Create(() => "Inner result", "InnerFunction");
        var innerResponses = new Queue<ChatResponse>(
        [
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("inner", innerFunction.Name)])),
            new(new ChatMessage(ChatRole.Assistant, "Inner complete")),
        ]);
        var innerAgent = new ChatClientAgent(CreateMockChatClient(innerResponses).Object, tools: [innerFunction]).AsBuilder()
            .Use((agent, context, next, cancellationToken) =>
            {
                innerInvocations.Add(context.Function.Name);
                return next(context, cancellationToken);
            }).Build();

        var outerFunction = AIFunctionFactory.Create(async () =>
        {
            await Task.Yield();
            var response = nestedStreaming
                ? await innerAgent.RunStreamingAsync("Run the inner function").ToAgentResponseAsync()
                : await innerAgent.RunAsync("Run the inner function");
            return response.Text;
        }, "OuterFunction");
        var outerResponses = new Queue<ChatResponse>(
        [
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("outer", outerFunction.Name)])),
            new(new ChatMessage(ChatRole.Assistant, "Outer complete")),
        ]);
        var outerAgent = new ChatClientAgent(CreateMockChatClient(outerResponses).Object, tools: [outerFunction]).AsBuilder()
            .Use((agent, context, next, cancellationToken) =>
            {
                outerInvocations.Add(context.Function.Name);
                return next(context, cancellationToken);
            }).Build();

        // Act
        var response = streaming
            ? await outerAgent.RunStreamingAsync("Run the outer function").ToAgentResponseAsync()
            : await outerAgent.RunAsync("Run the outer function");

        // Assert
        Assert.Equal([innerFunction.Name], innerInvocations);
        Assert.Equal([outerFunction.Name], outerInvocations);
        Assert.Equal("Inner complete", Assert.IsType<JsonElement>(response.Messages.SelectMany(m => m.Contents)
            .OfType<FunctionResultContent>().Single(r => r.CallId == "outer").Result).GetString());
        Assert.Empty(innerResponses);
        Assert.Empty(outerResponses);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RunAsync_ReplacingChatClientFactory_PreservesMiddlewareAsync(bool streaming)
    {
        // Arrange
        var invocations = new List<string>();
        var functionExecuted = false;
        var function = AIFunctionFactory.Create(() =>
        {
            functionExecuted = true;
            return "Function result";
        }, "DynamicFunction");
        var loader = AIFunctionFactory.Create(() =>
        {
            FunctionInvokingChatClient.CurrentContext!.Options!.Tools!.Add(function);
            return "Function added";
        }, "LoadFunction");
        var responses = new Queue<ChatResponse>(
        [
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("load", loader.Name)])),
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("invoke", function.Name)])),
            new(new ChatMessage(ChatRole.Assistant, "Complete")),
        ]);
        using var replacement = new FunctionInvokingChatClient(CreateMockChatClient(responses).Object);
        var originalClient = new Mock<IChatClient>();
        var first = new ChatClientAgent(originalClient.Object, tools: [loader]).AsBuilder()
            .Use((agent, context, next, cancellationToken) =>
            {
                invocations.Add($"First-{context.Function.Name}");
                return next(context, cancellationToken);
            }).Build();
        var agent = first.AsBuilder().Use((agent, context, next, cancellationToken) =>
        {
            invocations.Add($"Second-{context.Function.Name}");
            return context.Function.Name == function.Name
                ? new ValueTask<object?>("Handled by middleware")
                : next(context, cancellationToken);
        }).Build();
        var options = new ChatClientAgentRunOptions { ChatClientFactory = _ => replacement };

        // Act
        var response = streaming
            ? await agent.RunStreamingAsync("Run", options: options).ToAgentResponseAsync()
            : await agent.RunAsync("Run", options: options);

        // Assert
        Assert.Equal(["First-LoadFunction", "Second-LoadFunction", "First-DynamicFunction", "Second-DynamicFunction"], invocations);
        Assert.False(functionExecuted);
        Assert.Equal("Handled by middleware", response.Messages.SelectMany(m => m.Contents)
            .OfType<FunctionResultContent>().Single(r => r.CallId == "invoke").Result);
        Assert.Empty(responses);
        originalClient.Verify(c => c.GetResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Never);
        originalClient.Verify(c => c.GetStreamingResponseAsync(
            It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public async Task RunAsync_IndependentCapturedClient_DoesNotInheritMiddlewareAsync(bool streaming, bool nestedStreaming)
    {
        // Arrange
        var innerInvocations = new List<string>();
        var captured = await CaptureClientAsync(innerInvocations);
        using var innerClient = captured.Client;
        var innerFunction = AIFunctionFactory.Create(() => "Inner result", "InnerFunction");
        captured.Responses.Enqueue(new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("inner", innerFunction.Name)])));
        captured.Responses.Enqueue(new(new ChatMessage(ChatRole.Assistant, "Complete")));
        var outerFunction = AIFunctionFactory.Create(async () =>
        {
            var options = new ChatOptions { Tools = [innerFunction] };
            if (nestedStreaming)
            {
                await foreach (var _ in innerClient.GetStreamingResponseAsync([new(ChatRole.User, "Inner")], options))
                {
                }
            }
            else
            {
                await innerClient.GetResponseAsync([new(ChatRole.User, "Inner")], options);
            }

            return "Outer result";
        }, "OuterFunction");
        var outerInvocations = new List<string>();
        var responses = new Queue<ChatResponse>(
        [
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("outer", outerFunction.Name)])),
            new(new ChatMessage(ChatRole.Assistant, "Complete")),
        ]);
        var agent = new ChatClientAgent(CreateMockChatClient(responses).Object, tools: [outerFunction]).AsBuilder()
            .Use((agent, context, next, cancellationToken) =>
            {
                outerInvocations.Add(context.Function.Name);
                return next(context, cancellationToken);
            }).Build();

        // Act
        if (streaming)
        {
            await agent.RunStreamingAsync("Run").ToAgentResponseAsync();
        }
        else
        {
            await agent.RunAsync("Run");
        }

        // Assert
        Assert.Equal([outerFunction.Name], outerInvocations);
        Assert.Equal([innerFunction.Name], innerInvocations);
        Assert.Empty(responses);
        Assert.Empty(captured.Responses);
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    [InlineData(true, true)]
    public async Task RunAsync_OpaqueFunctionDecorator_DoesNotDuplicateMiddlewareAsync(bool streaming, bool invokeTwice)
    {
        // Arrange
        var invocations = new List<string>();
        var invocationCount = 0;
        var replaced = false;
        var function = AIFunctionFactory.Create(() => ++invocationCount, "TestFunction");
        var responses = new Queue<ChatResponse>(
        [
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("first", function.Name)])),
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("second", function.Name)])),
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("third", function.Name)])),
            new(new ChatMessage(ChatRole.Assistant, "Complete")),
        ]);
        var first = new ChatClientAgent(CreateMockChatClient(responses).Object, tools: [function]).AsBuilder()
            .Use(async (agent, context, next, cancellationToken) =>
            {
                invocations.Add("First");
                if (!replaced)
                {
                    replaced = true;
                    context.Options!.Tools = [new OpaqueFunction(context.Function)];
                }

                var result = await next(context, cancellationToken);
                return invokeTwice ? await next(context, cancellationToken) : result;
            }).Build();
        var agent = first.AsBuilder().Use((agent, context, next, cancellationToken) =>
        {
            invocations.Add("Second");
            return next(context, cancellationToken);
        }).Build();

        // Act
        if (streaming)
        {
            await agent.RunStreamingAsync("Run").ToAgentResponseAsync();
        }
        else
        {
            await agent.RunAsync("Run");
        }

        // Assert
        string[] expectedPerInvocation = invokeTwice ? ["First", "Second", "Second"] : ["First", "Second"];
        Assert.Equal(Enumerable.Range(0, 3).SelectMany(_ => expectedPerInvocation), invocations);
        Assert.Equal(invokeTwice ? 6 : 3, invocationCount);
        Assert.Empty(responses);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ChatClient_FailedFactory_DoesNotLeakMiddlewareAsync(bool returnsNull)
    {
        // Arrange
        var invocations = new List<string>();
        var function = AIFunctionFactory.Create(() => "Function result", "TestFunction");
        var responses = new Queue<ChatResponse>(
        [
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("invoke", function.Name)])),
            new(new ChatMessage(ChatRole.Assistant, "Complete")),
        ]);
        using var client = new FunctionInvokingChatClient(CreateMockChatClient(responses).Object);
        var expectedFailure = new InvalidOperationException("Factory failed");
        var failingFactory = await CaptureFactoryAsync("Failed", _ => returnsNull ? null! : throw expectedFailure);
        var successfulFactory = await CaptureFactoryAsync("Successful", null);

        // Act
        if (returnsNull)
        {
            Assert.Throws<InvalidOperationException>(() => failingFactory(client));
        }
        else
        {
            Assert.Same(expectedFailure, Assert.Throws<InvalidOperationException>(() => failingFactory(client)));
        }

        using var pipeline = successfulFactory(client);
        await pipeline.GetResponseAsync([new(ChatRole.User, "Run")], new ChatOptions { Tools = [function] });

        // Assert
        Assert.Equal(["Successful"], invocations);
        Assert.Empty(responses);

        async Task<Func<IChatClient, IChatClient>> CaptureFactoryAsync(string name, Func<IChatClient, IChatClient>? factory)
        {
            Func<IChatClient, IChatClient>? capturedFactory = null;
            var capturingAgent = new AnonymousDelegatingAIAgent(
                new ChatClientAgent(client),
                (messages, session, options, agent, cancellationToken) =>
                {
                    capturedFactory = Assert.IsType<ChatClientAgentRunOptions>(options).ChatClientFactory;
                    return Task.FromResult(new AgentResponse(new ChatMessage(ChatRole.Assistant, "Captured")));
                },
                runStreamingFunc: null);
            var agent = capturingAgent.AsBuilder().Use((agent, context, next, cancellationToken) =>
            {
                invocations.Add(name);
                return next(context, cancellationToken);
            }).Build();
            await agent.RunAsync("Capture", options: new ChatClientAgentRunOptions { ChatClientFactory = factory });
            return Assert.IsType<Func<IChatClient, IChatClient>>(capturedFactory);
        }
    }

    [Theory]
    [InlineData(false, "Completed")]
    [InlineData(false, "Faulted")]
    [InlineData(false, "Canceled")]
    [InlineData(true, "Completed")]
    [InlineData(true, "Faulted")]
    [InlineData(true, "Canceled")]
    [InlineData(true, "Disposed")]
    public async Task ChatClient_RequestScope_RestoresCallerContextAsync(bool streaming, string outcome)
    {
        // Arrange
        var firstInvocations = new List<string>();
        var secondInvocations = new List<string>();
        var first = await CaptureClientAsync(firstInvocations);
        var second = await CaptureClientAsync(secondInvocations);
        using var firstClient = first.Client;
        using var secondClient = second.Client;
        var firstFunction = AIFunctionFactory.Create(() => "First result", "FirstFunction");
        var secondFunction = AIFunctionFactory.Create(() => "Second result", "SecondFunction");
        var firstOptions = new ChatOptions { Tools = [firstFunction] };
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        var token = outcome == "Canceled" ? cancellation.Token : CancellationToken.None;
        Exception? expectedFailure = outcome switch
        {
            "Faulted" => new InvalidOperationException("Request failed"),
            "Canceled" => new OperationCanceledException(token),
            _ => null,
        };
        if (expectedFailure is not null)
        {
            first.Mock.Setup(c => c.GetResponseAsync(
                    It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
                .ThrowsAsync(expectedFailure);
            first.Mock.Setup(c => c.GetStreamingResponseAsync(
                    It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
                .Returns(FailingResponseAsync(expectedFailure));
        }
        else
        {
            if (outcome == "Completed")
            {
                first.Responses.Enqueue(new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("first", firstFunction.Name)])));
            }

            first.Responses.Enqueue(new(new ChatMessage(ChatRole.Assistant, "Complete")));
        }

        var callerContext = AIAgent.CurrentRunContext;
        var secondRequestCount = 0;

        // Act
        if (outcome == "Disposed")
        {
            await using var iterator = firstClient.GetStreamingResponseAsync([new(ChatRole.User, "First")], firstOptions).GetAsyncEnumerator();
            Assert.True(await iterator.MoveNextAsync());
            await VerifySecondClientAsync();
        }
        else
        {
            var observedFailure = false;
            try
            {
                if (streaming)
                {
                    await foreach (var _ in firstClient.GetStreamingResponseAsync([new(ChatRole.User, "First")], firstOptions, token))
                    {
                    }
                }
                else
                {
                    await firstClient.GetResponseAsync([new(ChatRole.User, "First")], firstOptions, token);
                }
            }
            catch (InvalidOperationException exception) when (ReferenceEquals(exception, expectedFailure))
            {
                observedFailure = true;
            }
            catch (OperationCanceledException) when (outcome == "Canceled")
            {
                observedFailure = true;
            }

            Assert.Equal(expectedFailure is not null, observedFailure);
        }

        // Assert
        await VerifySecondClientAsync();
        Assert.Equal(outcome == "Completed" ? new[] { firstFunction.Name } : [], firstInvocations);

        async Task VerifySecondClientAsync()
        {
            // Invoke clients directly under the same run context so a new agent run cannot mask a leaked scope.
            Assert.Same(callerContext, AIAgent.CurrentRunContext);
            second.Responses.Enqueue(new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("second", secondFunction.Name)])));
            second.Responses.Enqueue(new(new ChatMessage(ChatRole.Assistant, "Complete")));
            var response = await secondClient.GetResponseAsync(
                [new(ChatRole.User, "Second")], new ChatOptions { Tools = [secondFunction] });

            Assert.Equal("Second result", Assert.IsType<JsonElement>(Assert.Single(response.Messages
                .SelectMany(m => m.Contents).OfType<FunctionResultContent>()).Result).GetString());
            Assert.DoesNotContain(secondFunction.Name, firstInvocations);
            Assert.Equal(++secondRequestCount, secondInvocations.Count);
            Assert.All(secondInvocations, name => Assert.Equal(secondFunction.Name, name));
            Assert.Same(callerContext, AIAgent.CurrentRunContext);
        }

        static async IAsyncEnumerable<ChatResponseUpdate> FailingResponseAsync(Exception exception)
        {
            await Task.Yield();
            await Task.FromException(exception);
            yield break;
        }
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task RunAsync_ToolReplacementBeforeFailure_PreservesFunctionMiddlewareAsync(bool streaming)
    {
        // Arrange
        var invocations = new List<string>();
        var functionExecuted = false;
        var function = AIFunctionFactory.Create(() =>
        {
            functionExecuted = true;
            return "Function result";
        }, "DynamicFunction");
        var expectedFailure = new InvalidOperationException("Loader failed after updating tools");
        string LoadFunction()
        {
            FunctionInvokingChatClient.CurrentContext!.Options!.Tools = [function];
            throw expectedFailure;
        }

        var loader = AIFunctionFactory.Create(LoadFunction);
        var responses = new Queue<ChatResponse>(
        [
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("load", loader.Name)])),
            new(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("invoke", function.Name)])),
            new(new ChatMessage(ChatRole.Assistant, "Complete")),
        ]);
        using var client = new FunctionInvokingChatClient(CreateMockChatClient(responses).Object)
        {
            MaximumConsecutiveErrorsPerRequest = 1,
        };
        var agent = new ChatClientAgent(client, new ChatClientAgentOptions
        {
            UseProvidedChatClientAsIs = true,
            ChatOptions = new() { Tools = [loader] },
        }).AsBuilder().Use((agent, context, next, cancellationToken) =>
        {
            invocations.Add(context.Function.Name);
            return context.Function.Name == function.Name
                ? new ValueTask<object?>("Handled by middleware")
                : next(context, cancellationToken);
        }).Build();

        // Act
        var response = streaming
            ? await agent.RunStreamingAsync("Run the functions").ToAgentResponseAsync()
            : await agent.RunAsync("Run the functions");

        // Assert
        Assert.Equal([loader.Name, function.Name], invocations);
        Assert.False(functionExecuted);
        var results = response.Messages.SelectMany(m => m.Contents).OfType<FunctionResultContent>().ToArray();
        Assert.Same(expectedFailure, Assert.Single(results, result => result.CallId == "load").Exception);
        Assert.Equal("Handled by middleware", Assert.Single(results, result => result.CallId == "invoke").Result);
        Assert.Empty(responses);
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

    #region Function Replacement Tests

    /// <summary>
    /// Tests that a callback replacing the context function has that replacement invoked by the continuation.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareReplacesFunction_ReplacementInvokedAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var originalFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Original-Executed");
            return "Original result";
        }, "TestFunction", "A test function");
        var replacementFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Replacement-Executed");
            return "Replacement result";
        }, "ReplacementFunction", "A replacement function");

        var (mockChatClient, requests) = CreateMockChatClientForFunctionCall("TestFunction");
        var innerAgent = new ChatClientAgent(mockChatClient.Object);

        ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            context.Function = replacementFunction;
            return next(context, cancellationToken);
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [originalFunction] });
        await middleware.RunAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None);

        // Assert
        Assert.Equal(["Replacement-Executed"], executionOrder);
        Assert.Equal(2, requests.Count);
        Assert.Equal("Replacement result", GetFunctionResult(requests[1]));
    }

    /// <summary>
    /// Tests that a callback replacing the context function has that replacement invoked during streaming runs.
    /// </summary>
    [Fact]
    public async Task RunStreamingAsync_MiddlewareReplacesFunction_ReplacementInvokedAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var originalFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Original-Executed");
            return "Original result";
        }, "TestFunction", "A test function");
        var replacementFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Replacement-Executed");
            return "Replacement result";
        }, "ReplacementFunction", "A replacement function");

        var (mockChatClient, requests) = CreateMockChatClientForFunctionCall("TestFunction");
        var innerAgent = new ChatClientAgent(mockChatClient.Object);

        ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            context.Function = replacementFunction;
            return next(context, cancellationToken);
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [originalFunction] });
        var updates = new List<AgentResponseUpdate>();
        await foreach (var update in middleware.RunStreamingAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None))
        {
            updates.Add(update);
        }

        // Assert
        Assert.NotEmpty(updates);
        Assert.Equal(["Replacement-Executed"], executionOrder);
        Assert.Equal(2, requests.Count);
        Assert.Equal("Replacement result", GetFunctionResult(requests[1]));
    }

    /// <summary>
    /// Tests that a replacement made by the first callback is invoked without running the later callbacks.
    /// </summary>
    [Fact]
    public async Task RunAsync_FirstMiddlewareReplacesFunction_LaterMiddlewareNotInvokedAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var originalFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Original-Executed");
            return "Original result";
        }, "TestFunction", "A test function");
        var replacementFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Replacement-Executed");
            return "Replacement result";
        }, "ReplacementFunction", "A replacement function");

        var (mockChatClient, requests) = CreateMockChatClientForFunctionCall("TestFunction");
        var innerAgent = new ChatClientAgent(mockChatClient.Object);

        ValueTask<object?> FirstMiddlewareAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("First-Pre");
            context.Function = replacementFunction;
            return next(context, cancellationToken);
        }

        ValueTask<object?> SecondMiddlewareAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("Second-Pre");
            return next(context, cancellationToken);
        }

        var firstMiddleware = new FunctionInvocationDelegatingAgent(innerAgent, FirstMiddlewareAsync);
        var secondMiddleware = new FunctionInvocationDelegatingAgent(firstMiddleware, SecondMiddlewareAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [originalFunction] });
        await secondMiddleware.RunAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None);

        // Assert
        Assert.Equal(["First-Pre", "Replacement-Executed"], executionOrder);
        Assert.Equal(2, requests.Count);
        Assert.Equal("Replacement result", GetFunctionResult(requests[1]));
    }

    /// <summary>
    /// Tests that a replacement made by the last callback is invoked instead of the original function.
    /// </summary>
    [Fact]
    public async Task RunAsync_LastMiddlewareReplacesFunction_ReplacementInvokedAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var originalFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Original-Executed");
            return "Original result";
        }, "TestFunction", "A test function");
        var replacementFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Replacement-Executed");
            return "Replacement result";
        }, "ReplacementFunction", "A replacement function");

        var (mockChatClient, requests) = CreateMockChatClientForFunctionCall("TestFunction");
        var innerAgent = new ChatClientAgent(mockChatClient.Object);

        async ValueTask<object?> FirstMiddlewareAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("First-Pre");
            var result = await next(context, cancellationToken);
            executionOrder.Add("First-Post");
            return result;
        }

        ValueTask<object?> SecondMiddlewareAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("Second-Pre");
            context.Function = replacementFunction;
            return next(context, cancellationToken);
        }

        var firstMiddleware = new FunctionInvocationDelegatingAgent(innerAgent, FirstMiddlewareAsync);
        var secondMiddleware = new FunctionInvocationDelegatingAgent(firstMiddleware, SecondMiddlewareAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [originalFunction] });
        await secondMiddleware.RunAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None);

        // Assert
        Assert.Equal(["First-Pre", "Second-Pre", "Replacement-Executed", "First-Post"], executionOrder);
        Assert.Equal("Replacement result", GetFunctionResult(requests[1]));
    }

    /// <summary>
    /// Tests that wrapping a replacement with the pending callbacks lets the later callbacks run for it.
    /// </summary>
    [Fact]
    public async Task RunAsync_ReplacementWrappedWithPendingMiddleware_LaterMiddlewareInvokedAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var originalFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Original-Executed");
            return "Original result";
        }, "TestFunction", "A test function");
        var replacementFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Replacement-Executed");
            return "Replacement result";
        }, "ReplacementFunction", "A replacement function");

        var (mockChatClient, requests) = CreateMockChatClientForFunctionCall("TestFunction");
        var innerAgent = new ChatClientAgent(mockChatClient.Object);

        ValueTask<object?> FirstMiddlewareAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("First-Pre");
            context.Function = context.WrapWithPendingMiddleware(replacementFunction);
            return next(context, cancellationToken);
        }

        async ValueTask<object?> SecondMiddlewareAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("Second-Pre");
            var result = await next(context, cancellationToken);
            executionOrder.Add("Second-Post");
            return result;
        }

        var firstMiddleware = new FunctionInvocationDelegatingAgent(innerAgent, FirstMiddlewareAsync);
        var secondMiddleware = new FunctionInvocationDelegatingAgent(firstMiddleware, SecondMiddlewareAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [originalFunction] });
        await secondMiddleware.RunAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None);

        // Assert
        Assert.Equal(["First-Pre", "Second-Pre", "Replacement-Executed", "Second-Post"], executionOrder);
        Assert.Equal("Replacement result", GetFunctionResult(requests[1]));
    }

    /// <summary>
    /// Tests that wrapping a replacement returns it unchanged when no other callbacks are pending.
    /// </summary>
    [Fact]
    public async Task RunAsync_WrapWithPendingMiddleware_NoPendingMiddleware_ReturnsSameFunctionAsync()
    {
        // Arrange
        var originalFunction = AIFunctionFactory.Create(() => "Original result", "TestFunction", "A test function");
        var replacementFunction = AIFunctionFactory.Create(() => "Replacement result", "ReplacementFunction", "A replacement function");
        AIFunction? wrappedFunction = null;

        var (mockChatClient, _) = CreateMockChatClientForFunctionCall("TestFunction");
        var innerAgent = new ChatClientAgent(mockChatClient.Object);

        ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            wrappedFunction = context.WrapWithPendingMiddleware(replacementFunction);
            context.Function = wrappedFunction;
            return next(context, cancellationToken);
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [originalFunction] });
        await middleware.RunAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None);

        // Assert
        Assert.Same(replacementFunction, wrappedFunction);
    }

    /// <summary>
    /// Tests that a replacement is invoked when the function is called without an ambient invocation context.
    /// </summary>
    [Fact]
    public async Task RunAsync_DirectFunctionInvocation_MiddlewareReplacesFunctionAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var originalFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Original-Executed");
            return "Original result";
        }, "TestFunction", "A test function");
        var replacementFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Replacement-Executed");
            return "Replacement result";
        }, "ReplacementFunction", "A replacement function");

        object? directResult = null;
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns(GetResponseAsync);

        async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken ct)
        {
            // Invoke the function directly so that no FunctionInvokingChatClient context exists.
            if (options?.Tools?.FirstOrDefault() is AIFunction function)
            {
                directResult = await function.InvokeAsync([], ct);
            }

            return new ChatResponse([new ChatMessage(ChatRole.Assistant, "Response after direct invocation")]);
        }

        var innerAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            UseProvidedChatClientAsIs = true
        });

        ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            context.Function = replacementFunction;
            return next(context, cancellationToken);
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [originalFunction] });
        await middleware.RunAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None);

        // Assert
        Assert.Equal(["Replacement-Executed"], executionOrder);
        Assert.Equal("Replacement result", directResult?.ToString());
    }

    /// <summary>
    /// Tests that the original function is still invoked when a callback leaves the context function unchanged.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareKeepsFunction_OriginalInvokedAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var originalFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Original-Executed");
            return "Original result";
        }, "TestFunction", "A test function");

        var (mockChatClient, requests) = CreateMockChatClientForFunctionCall("TestFunction");
        var innerAgent = new ChatClientAgent(mockChatClient.Object);
        AIFunction? requestedFunction = null;

        ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            // Reassigning the same function must not change which function is invoked.
            requestedFunction = context.Function;
            context.Function = requestedFunction;
            return next(context, cancellationToken);
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [originalFunction] });
        await middleware.RunAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None);

        // Assert
        Assert.NotNull(requestedFunction);
        Assert.Equal(["Original-Executed"], executionOrder);
        Assert.Equal("Original result", GetFunctionResult(requests[1]));
    }

    /// <summary>
    /// Tests that wrapping a function outside of a callback invocation throws.
    /// </summary>
    [Fact]
    public void WrapWithPendingMiddleware_NoActiveInvocation_Throws()
    {
        // Arrange
        var function = AIFunctionFactory.Create(() => "Result", "TestFunction", "A test function");
        var context = new FunctionInvocationContext { Function = function };

        // Act & Assert
        Assert.Throws<InvalidOperationException>(() => context.WrapWithPendingMiddleware(function));
    }

    /// <summary>
    /// Tests that wrapping validates its arguments.
    /// </summary>
    [Fact]
    public void WrapWithPendingMiddleware_NullArguments_ThrowsArgumentNullException()
    {
        // Arrange
        var function = AIFunctionFactory.Create(() => "Result", "TestFunction", "A test function");
        var context = new FunctionInvocationContext { Function = function };

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => ((FunctionInvocationContext)null!).WrapWithPendingMiddleware(function));
        Assert.Throws<ArgumentNullException>(() => context.WrapWithPendingMiddleware(null!));
    }

    /// <summary>
    /// Tests that wrapping throws once the callback called its continuation, because the pending callbacks ran.
    /// </summary>
    [Fact]
    public async Task RunAsync_WrapWithPendingMiddleware_AfterContinuation_ThrowsAsync()
    {
        // Arrange
        var originalFunction = AIFunctionFactory.Create(() => "Original result", "TestFunction", "A test function");
        var replacementFunction = AIFunctionFactory.Create(() => "Replacement result", "ReplacementFunction", "A replacement function");
        Exception? capturedException = null;

        var (mockChatClient, _) = CreateMockChatClientForFunctionCall("TestFunction");
        var innerAgent = new ChatClientAgent(mockChatClient.Object);

        async ValueTask<object?> FirstMiddlewareAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            var result = await next(context, cancellationToken);
            capturedException = Record.Exception(() => context.WrapWithPendingMiddleware(replacementFunction));
            return result;
        }

        ValueTask<object?> SecondMiddlewareAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
            => next(context, cancellationToken);

        var firstMiddleware = new FunctionInvocationDelegatingAgent(innerAgent, FirstMiddlewareAsync);
        var secondMiddleware = new FunctionInvocationDelegatingAgent(firstMiddleware, SecondMiddlewareAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [originalFunction] });
        await secondMiddleware.RunAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None);

        // Assert
        Assert.IsType<InvalidOperationException>(capturedException);
    }

    /// <summary>
    /// Tests that wrapping throws from an execution context that outlived the callback that created it.
    /// </summary>
    [Fact]
    public async Task RunAsync_WrapWithPendingMiddleware_FromEscapedExecutionContext_ThrowsAsync()
    {
        // Arrange
        var originalFunction = AIFunctionFactory.Create(() => "Original result", "TestFunction", "A test function");
        var replacementFunction = AIFunctionFactory.Create(() => "Replacement result", "ReplacementFunction", "A replacement function");
        var callbackReturned = new TaskCompletionSource<bool>();
        Task<Exception?>? escapedWork = null;

        var (mockChatClient, _) = CreateMockChatClientForFunctionCall("TestFunction");
        var innerAgent = new ChatClientAgent(mockChatClient.Object);

        ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            // Background work started by the callback inherits its execution context, and therefore its scope.
            escapedWork = Task.Run(async () =>
            {
                await callbackReturned.Task;
                return Record.Exception(() => context.WrapWithPendingMiddleware(replacementFunction));
            });

            return next(context, cancellationToken);
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [originalFunction] });
        await middleware.RunAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None);
        callbackReturned.SetResult(true);

        // Assert
        Assert.NotNull(escapedWork);
        Assert.IsType<InvalidOperationException>(await escapedWork);
    }

    /// <summary>
    /// Tests that a callback calling its continuation twice runs the later callbacks for both calls,
    /// even when one of them replaced the function.
    /// </summary>
    [Fact]
    public async Task RunAsync_RepeatedContinuation_AfterReplacement_InvokesLaterMiddlewareAgainAsync()
    {
        // Arrange
        var executionOrder = new List<string>();
        var originalFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Original-Executed");
            return "Original result";
        }, "TestFunction", "A test function");
        var replacementFunction = AIFunctionFactory.Create(() =>
        {
            executionOrder.Add("Replacement-Executed");
            return "Replacement result";
        }, "ReplacementFunction", "A replacement function");

        var (mockChatClient, _) = CreateMockChatClientForFunctionCall("TestFunction");
        var innerAgent = new ChatClientAgent(mockChatClient.Object);

        async ValueTask<object?> FirstMiddlewareAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("First-Pre");
            _ = await next(context, cancellationToken);
            executionOrder.Add("First-Between");
            return await next(context, cancellationToken);
        }

        ValueTask<object?> SecondMiddlewareAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            executionOrder.Add("Second-Pre");
            context.Function = replacementFunction;
            return next(context, cancellationToken);
        }

        var firstMiddleware = new FunctionInvocationDelegatingAgent(innerAgent, FirstMiddlewareAsync);
        var secondMiddleware = new FunctionInvocationDelegatingAgent(firstMiddleware, SecondMiddlewareAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [originalFunction] });
        await secondMiddleware.RunAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None);

        // Assert - the second call goes through the later callback again instead of invoking its replacement directly.
        Assert.Equal(
            ["First-Pre", "Second-Pre", "Replacement-Executed", "First-Between", "Second-Pre", "Replacement-Executed"],
            executionOrder);
        Assert.DoesNotContain("Original-Executed", executionOrder);
    }

    /// <summary>
    /// Tests that the function requested by the model is restored on the context once the callbacks completed.
    /// </summary>
    [Fact]
    public async Task RunAsync_MiddlewareReplacesFunction_RequestedFunctionRestoredAsync()
    {
        // Arrange
        var originalFunction = AIFunctionFactory.Create(() => "Original result", "TestFunction", "A test function");
        var replacementFunction = AIFunctionFactory.Create(() => "Replacement result", "ReplacementFunction", "A replacement function");
        AIFunction? requestedFunction = null;
        FunctionInvocationContext? capturedContext = null;

        var (mockChatClient, _) = CreateMockChatClientForFunctionCall("TestFunction");
        var innerAgent = new ChatClientAgent(mockChatClient.Object);

        ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            capturedContext = context;
            requestedFunction = context.Function;
            context.Function = replacementFunction;
            return next(context, cancellationToken);
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [originalFunction] });
        await middleware.RunAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None);

        // Assert - telemetry and logging read the function after the invocation, so it must be the requested one.
        Assert.NotNull(capturedContext);
        Assert.Same(requestedFunction, capturedContext.Function);
    }

    /// <summary>
    /// Tests that redirecting a directly invoked function to another wrapped function completes
    /// instead of re-entering the same callback endlessly.
    /// </summary>
    [Fact]
    public async Task RunAsync_DirectFunctionInvocation_ReplacementIsAnotherWrappedFunction_DoesNotRecurseAsync()
    {
        // Arrange
        var callbackCount = 0;
        var firstFunction = AIFunctionFactory.Create(() => "First result", "FirstFunction", "The requested function");
        var secondFunction = AIFunctionFactory.Create(() => "Second result", "SecondFunction", "The function to redirect to");
        object? directResult = null;

        AIFunction? wrappedSecondFunction = null;
        var mockChatClient = new Mock<IChatClient>();
        mockChatClient.Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Returns(GetResponseAsync);

        async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken ct)
        {
            // Invoke the wrapped function directly so that no FunctionInvokingChatClient context exists.
            if (options?.Tools is { Count: 2 } tools)
            {
                wrappedSecondFunction = (AIFunction)tools[1];
                directResult = await ((AIFunction)tools[0]).InvokeAsync([], ct);
            }

            return new ChatResponse([new ChatMessage(ChatRole.Assistant, "Response after direct invocation")]);
        }

        var innerAgent = new ChatClientAgent(mockChatClient.Object, new ChatClientAgentOptions
        {
            UseProvidedChatClientAsIs = true
        });

        ValueTask<object?> MiddlewareCallbackAsync(AIAgent agent, FunctionInvocationContext context, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>> next, CancellationToken cancellationToken)
        {
            callbackCount++;

            // Unconditionally redirect to the other wrapped tool, which leads back to this callback.
            context.Function = wrappedSecondFunction!;
            return next(context, cancellationToken);
        }

        var middleware = new FunctionInvocationDelegatingAgent(innerAgent, MiddlewareCallbackAsync);

        // Act
        var options = new ChatClientAgentRunOptions(new ChatOptions { Tools = [firstFunction, secondFunction] });
        await middleware.RunAsync([new(ChatRole.User, "Test message")], null, options, CancellationToken.None);

        // Assert
        Assert.Equal("Second result", directResult?.ToString());
        Assert.Equal(1, callbackCount);
    }

    #endregion

    /// <summary>
    /// Creates a mock IChatClient that requests a single function call and then completes, capturing every request.
    /// </summary>
    /// <param name="functionName">The name of the function to request.</param>
    /// <returns>The mock and the list of message sequences received by it.</returns>
    private static (Mock<IChatClient> Mock, List<List<ChatMessage>> Requests) CreateMockChatClientForFunctionCall(string functionName)
    {
        var mockChatClient = new Mock<IChatClient>();
        var requests = new List<List<ChatMessage>>();

        ChatResponse CreateResponse(IEnumerable<ChatMessage> messages)
        {
            requests.Add([.. messages]);
            return requests.Count == 1
                ? new ChatResponse([new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("call_123", functionName, new Dictionary<string, object?>())])])
                : new ChatResponse([new ChatMessage(ChatRole.Assistant, "Final response")]);
        }

        mockChatClient.Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken) => CreateResponse(messages));

        mockChatClient.Setup(c => c.GetStreamingResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Returns((IEnumerable<ChatMessage> messages, ChatOptions? options, CancellationToken cancellationToken) =>
                CreateResponse(messages).ToChatResponseUpdates().ToAsyncEnumerable());

        return (mockChatClient, requests);
    }

    /// <summary>
    /// Gets the single function result sent back to the chat client.
    /// </summary>
    /// <param name="messages">The messages of a request received by the chat client.</param>
    /// <returns>The function result value.</returns>
    private static string? GetFunctionResult(List<ChatMessage> messages)
        => Assert.Single(messages.SelectMany(m => m.Contents).OfType<FunctionResultContent>()).Result?.ToString();

    private static async Task<(IChatClient Client, Mock<IChatClient> Mock, Queue<ChatResponse> Responses)> CaptureClientAsync(List<string> invocations)
    {
        var responses = new Queue<ChatResponse>([new(new ChatMessage(ChatRole.Assistant, "Initialized"))]);
        var mock = CreateMockChatClient(responses);
        IChatClient? capturedClient = null;
        var capturingAgent = new AnonymousDelegatingAIAgent(
            new ChatClientAgent(mock.Object),
            (messages, session, options, innerAgent, cancellationToken) =>
            {
                var runOptions = Assert.IsType<ChatClientAgentRunOptions>(options?.Clone());
                var factory = Assert.IsType<Func<IChatClient, IChatClient>>(runOptions.ChatClientFactory);
                runOptions.ChatClientFactory = client => capturedClient = factory(client);
                return innerAgent.RunAsync(messages, session, runOptions, cancellationToken);
            },
            runStreamingFunc: null);
        var agent = capturingAgent.AsBuilder()
            .Use((agent, context, next, cancellationToken) =>
            {
                invocations.Add(context.Function.Name);
                return next(context, cancellationToken);
            }).Build();
        await agent.RunAsync("Initialize");
        return (Assert.IsAssignableFrom<IChatClient>(capturedClient), mock, responses);
    }

    private sealed class OpaqueFunction(AIFunction innerFunction) : DelegatingAIFunction(innerFunction)
    {
        public override object? GetService(Type serviceType, object? serviceKey = null)
            => serviceKey is null && serviceType.IsInstanceOfType(this) ? this : null;
    }

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

    private sealed class OpaqueChatClient(IChatClient innerClient) : DelegatingChatClient(innerClient)
    {
        public override object? GetService(Type serviceType, object? serviceKey = null)
            => serviceKey is null && serviceType.IsInstanceOfType(this) ? this : null;
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
