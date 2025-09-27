// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests.Middleware;

/// <summary>
/// Helper utilities for testing middleware functionality.
/// </summary>
public static class MiddlewareTestHelpers
{
    /// <summary>
    /// Creates a mock IChatClient with predefined responses for testing.
    /// </summary>
    /// <param name="responses">The responses to return in sequence.</param>
    /// <returns>A configured mock IChatClient.</returns>
    public static Mock<IChatClient> CreateMockChatClient(params ChatResponse[] responses)
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
    public static Mock<IChatClient> CreateMockChatClientWithFunctionCalls(params FunctionCallContent[] functionCalls)
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
    /// Creates a ChatResponse with FunctionCallContent for testing function calling scenarios.
    /// </summary>
    /// <param name="functionName">The name of the function to call.</param>
    /// <param name="arguments">The arguments for the function call.</param>
    /// <param name="callId">The call ID for the function call.</param>
    /// <returns>A ChatResponse containing the function call.</returns>
    public static ChatResponse CreateFunctionCallResponse(string functionName, IDictionary<string, object?>? arguments = null, string? callId = null)
    {
        callId ??= Guid.NewGuid().ToString();
        arguments ??= new Dictionary<string, object?>();

        var functionCall = new FunctionCallContent(callId, functionName, arguments);
        return new ChatResponse([new ChatMessage(ChatRole.Assistant, [functionCall])]);
    }

    /// <summary>
    /// Creates a ChatResponse with multiple function calls for testing complex scenarios.
    /// </summary>
    /// <param name="functionCalls">The function calls to include.</param>
    /// <returns>A ChatResponse containing all function calls.</returns>
    public static ChatResponse CreateMultipleFunctionCallResponse(params (string functionName, IDictionary<string, object?>? arguments, string? callId)[] functionCalls)
    {
        var contents = functionCalls.Select(fc =>
        {
            var callId = fc.callId ?? Guid.NewGuid().ToString();
            var arguments = fc.arguments ?? new Dictionary<string, object?>();
            return (AIContent)new FunctionCallContent(callId, fc.functionName, arguments);
        }).ToList();

        return new ChatResponse([new ChatMessage(ChatRole.Assistant, contents)]);
    }

    /// <summary>
    /// Creates a default ChatResponse for fallback scenarios.
    /// </summary>
    /// <returns>A default ChatResponse.</returns>
    public static ChatResponse CreateDefaultResponse()
    {
        return new ChatResponse([new ChatMessage(ChatRole.Assistant, "Default response")]);
    }

    /// <summary>
    /// Creates a ChatClientAgent with a mocked IChatClient for testing.
    /// </summary>
    /// <param name="mockChatClient">The mock chat client to use.</param>
    /// <param name="options">Optional agent options.</param>
    /// <returns>A ChatClientAgent for testing.</returns>
    public static ChatClientAgent CreateTestChatClientAgent(Mock<IChatClient>? mockChatClient = null, ChatClientAgentOptions? options = null)
    {
        mockChatClient ??= CreateMockChatClient(CreateDefaultResponse());
        options ??= new ChatClientAgentOptions();

        return new ChatClientAgent(mockChatClient.Object, options);
    }

    /// <summary>
    /// Creates an execution order tracker for testing run middleware execution sequence.
    /// </summary>
    /// <returns>A list to track execution order and helper methods.</returns>
    public static (List<string> executionOrder, Func<string, Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, AIAgent, CancellationToken, Task<AgentRunResponse>>> createRunMiddleware) CreateRunExecutionOrderTracker()
    {
        var executionOrder = new List<string>();

        Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, AIAgent, CancellationToken, Task<AgentRunResponse>> createRunMiddleware(string name)
        {
            return async (messages, thread, options, innerAgent, cancellationToken) =>
            {
                executionOrder.Add($"{name}-Pre");
                var result = await innerAgent.RunAsync(messages, thread, options, cancellationToken);
                executionOrder.Add($"{name}-Post");
                return result;
            };
        }

        return (executionOrder, createRunMiddleware);
    }

    /// <summary>
    /// Creates an execution order tracker for function invocation middleware.
    /// </summary>
    /// <returns>A list to track execution order and helper methods.</returns>
    public static (List<string> executionOrder, Func<string, Func<AIAgent, FunctionInvocationContext, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>>> createFunctionMiddleware) CreateFunctionExecutionOrderTracker()
    {
        var executionOrder = new List<string>();

        Func<AIAgent, FunctionInvocationContext, Func<FunctionInvocationContext, CancellationToken, ValueTask<object?>>, CancellationToken, ValueTask<object?>> createFunctionMiddleware(string name)
        {
            return async (agent, context, next, cancellationToken) =>
            {
                executionOrder.Add($"{name}-Pre");
                var result = await next(context, cancellationToken);
                executionOrder.Add($"{name}-Post");
                return result;
            };
        }

        return (executionOrder, createFunctionMiddleware);
    }

    /// <summary>
    /// Creates a test AIFunction for use in middleware testing.
    /// </summary>
    /// <param name="functionName">The name of the function.</param>
    /// <param name="returnValue">The value to return when the function is invoked.</param>
    /// <returns>An AIFunction for testing.</returns>
    public static AIFunction CreateTestFunction(string functionName = "TestFunction", object? returnValue = null)
    {
        returnValue ??= "Test function result";

        return AIFunctionFactory.Create(() => returnValue, functionName);
    }

    /// <summary>
    /// Creates test messages for agent invocation.
    /// </summary>
    /// <param name="messageCount">The number of messages to create.</param>
    /// <param name="messagePrefix">The prefix for message content.</param>
    /// <returns>A list of test messages.</returns>
    public static List<ChatMessage> CreateTestMessages(int messageCount = 1, string messagePrefix = "Test message")
    {
        var messages = new List<ChatMessage>();
        for (int i = 0; i < messageCount; i++)
        {
            messages.Add(new ChatMessage(ChatRole.User, $"{messagePrefix} {i + 1}"));
        }
        return messages;
    }

    /// <summary>
    /// Creates test AgentRunOptions with optional tools.
    /// </summary>
    /// <param name="tools">Optional tools to include in the options.</param>
    /// <returns>AgentRunOptions for testing.</returns>
    public static AgentRunOptions CreateTestRunOptions(IList<AITool>? tools = null)
    {
        return new AgentRunOptions();
    }

    /// <summary>
    /// Creates test ChatClientAgentRunOptions with optional tools and chat options.
    /// </summary>
    /// <param name="tools">Optional tools to include.</param>
    /// <param name="chatOptions">Optional chat options.</param>
    /// <returns>ChatClientAgentRunOptions for testing.</returns>
    public static ChatClientAgentRunOptions CreateTestChatClientRunOptions(IList<AITool>? tools = null, ChatOptions? chatOptions = null)
    {
        chatOptions ??= new ChatOptions();
        if (tools != null)
        {
            chatOptions.Tools = tools;
        }

        return new ChatClientAgentRunOptions(chatOptions);
    }

    /// <summary>
    /// Verifies that a mock was called with specific parameters.
    /// </summary>
    /// <param name="mockChatClient">The mock to verify.</param>
    /// <param name="expectedMessageCount">Expected number of messages.</param>
    /// <param name="times">Expected number of times the method was called.</param>
    public static void VerifyMockChatClientCalled(Mock<IChatClient> mockChatClient, int? expectedMessageCount = null, Times? times = null)
    {
        times ??= Times.Once();

        if (expectedMessageCount.HasValue)
        {
            mockChatClient.Verify(c => c.GetResponseAsync(
                It.Is<IEnumerable<ChatMessage>>(msgs => msgs.Count() == expectedMessageCount.Value),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()), times.Value);
        }
        else
        {
            mockChatClient.Verify(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()), times.Value);
        }
    }

    /// <summary>
    /// Creates a test scenario with middleware that modifies run parameters.
    /// </summary>
    /// <param name="modifyMessages">Whether to modify messages.</param>
    /// <param name="modifyOptions">Whether to modify options.</param>
    /// <returns>A middleware function that performs the specified modifications.</returns>
    public static Func<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, AIAgent, CancellationToken, Task<AgentRunResponse>> CreateRunModifyingMiddleware(bool modifyMessages = false, bool modifyOptions = false)
    {
        return async (messages, thread, options, innerAgent, cancellationToken) =>
        {
            var modifiedMessages = messages;
            var modifiedOptions = options;

            if (modifyMessages)
            {
                var messagesList = messages.ToList();
                messagesList.Insert(0, new ChatMessage(ChatRole.System, "Added by middleware"));
                modifiedMessages = messagesList;
            }

            if (modifyOptions)
            {
                modifiedOptions = CreateTestRunOptions();
            }

            return await innerAgent.RunAsync(modifiedMessages, thread, modifiedOptions, cancellationToken);
        };
    }
}
