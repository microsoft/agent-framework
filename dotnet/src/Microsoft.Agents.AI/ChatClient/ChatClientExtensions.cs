// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Provides extension methods for Creating an <see cref="AIAgent"/> from an <see cref="IChatClient"/>.
/// </summary>
public static class ChatClientExtensions
{
    /// <summary>
    /// Creates a new <see cref="ChatClientAgent"/> instance.
    /// </summary>
    /// <inheritdoc cref="ChatClientAgent(IChatClient, string?, string?, string?, IList{AITool}?, ILoggerFactory?, IServiceProvider?)"/>
    /// <returns>A new <see cref="ChatClientAgent"/> instance.</returns>
    public static ChatClientAgent AsAIAgent(
        this IChatClient chatClient,
        string? instructions = null,
        string? name = null,
        string? description = null,
        IList<AITool>? tools = null,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null) =>
        new(
            chatClient,
            instructions: instructions,
            name: name,
            description: description,
            tools: tools,
            loggerFactory: loggerFactory,
            services: services);

    /// <summary>
    /// Creates a new <see cref="ChatClientAgent"/> instance.
    /// </summary>
    /// <inheritdoc cref="ChatClientAgent(IChatClient, ChatClientAgentOptions?, ILoggerFactory?, IServiceProvider?)"/>
    /// <returns>A new <see cref="ChatClientAgent"/> instance.</returns>
    public static ChatClientAgent AsAIAgent(
        this IChatClient chatClient,
        ChatClientAgentOptions? options,
        ILoggerFactory? loggerFactory = null,
        IServiceProvider? services = null) =>
        new(chatClient, options, loggerFactory, services);

    internal static IChatClient WithDefaultAgentMiddleware(this IChatClient chatClient, ChatClientAgentOptions? options, IServiceProvider? services = null)
    {
        var chatBuilder = chatClient.AsBuilder();

        // ApprovalResponseBindingChatClient is registered first so that it sits as the outermost decorator,
        // above ApprovalNotRequiredFunctionBypassingChatClient and FunctionInvokingChatClient. ChatClientBuilder.Build
        // applies factories in reverse order, making the first Use() call outermost. Placing it outermost lets it
        // inspect the caller's raw approval responses before any framework-generated (auto-approved) responses are
        // injected below it, binding each response to the model-originated approval request the framework surfaced so
        // an approved call matches exactly what was surfaced for approval.
        if (options?.DisableApprovalResponseBinding is not true)
        {
            chatBuilder.Use((innerClient, services) =>
                new ApprovalResponseBindingChatClient(innerClient, services.GetService<ILoggerFactory>()));
        }

        // ApprovalNotRequiredFunctionBypassingChatClient is registered before FunctionInvokingChatClient so that
        // it sits above FICC in the pipeline. ChatClientBuilder.Build applies factories in reverse order,
        // making the first Use() call outermost. By adding this decorator here, the resulting pipeline is:
        //   [ApprovalResponseBindingChatClient] → ApprovalNotRequiredFunctionBypassingChatClient → FunctionInvokingChatClient
        //     → [MessageInjectingChatClient] → [PerServiceCallChatHistoryPersistingChatClient] → DeferredOpenTelemetryChatClient → leaf IChatClient
        // This allows the decorator to intercept FICC's responses and remove approval requests for tools
        // that don't actually require approval, storing them for automatic re-injection on the next request.
        if (options?.DisableApprovalNotRequiredFunctionBypassing is not true)
        {
            chatBuilder.Use((innerClient, services) =>
                new ApprovalNotRequiredFunctionBypassingChatClient(innerClient, services.GetService<ILoggerFactory>()));
        }

        if (chatClient.GetService<FunctionInvokingChatClient>() is null)
        {
            chatBuilder.Use((innerClient, services) =>
            {
                var loggerFactory = services.GetService<ILoggerFactory>();

                return new FunctionInvokingChatClient(innerClient, loggerFactory, services);
            });
        }

        // MessageInjectingChatClient is injected when EnableMessageInjection is enabled.
        // It is registered after FunctionInvokingChatClient so that it sits between FIC and the inner client.
        // ChatClientBuilder.Build applies factories in reverse order, making the first Use() call outermost.
        // MessageInjectingChatClient enables injecting messages during the function loop and looping when needed.
        if (options?.EnableMessageInjection is true)
        {
            chatBuilder.Use(innerClient => new MessageInjectingChatClient(innerClient));
        }

        // PerServiceCallChatHistoryPersistingChatClient is injected when RequirePerServiceCallChatHistoryPersistence is enabled.
        // It is registered after MessageInjectingChatClient (if present) so it sits closest to the leaf client.
        // The resulting pipeline is:
        //   FunctionInvokingChatClient → [MessageInjectingChatClient] → [PerServiceCallChatHistoryPersistingChatClient] → leaf IChatClient
        // PerServiceCallChatHistoryPersistingChatClient simulates service-stored chat history by loading history
        // before each service call, persisting after each call, and returning a sentinel ConversationId.
        if (options?.RequirePerServiceCallChatHistoryPersistence is true)
        {
            chatBuilder.Use(innerClient => new PerServiceCallChatHistoryPersistingChatClient(innerClient));
        }

        // DeferredOpenTelemetryChatClient is registered last so it sits as the innermost decorator, directly
        // above the leaf client and below FunctionInvokingChatClient. It is inert until an OpenTelemetryAgent
        // activates it. Placing OpenTelemetry below FICC ensures the chat span closes before tools are invoked,
        // so FICC emits execute_tool spans on the agent source.
        chatBuilder.Use(innerClient => new DeferredOpenTelemetryChatClient(innerClient));

        var agentChatClient = chatBuilder.Build(services);

        if (options?.ChatOptions?.Tools is { Count: > 0 })
        {
            // When tools are provided in the constructor, set the tools for the whole lifecycle of the chat client
            var functionService = agentChatClient.GetService<FunctionInvokingChatClient>();
            Debug.Assert(functionService is not null, "FunctionInvokingChatClient should be registered in the chat client.");
            functionService!.AdditionalTools = options.ChatOptions.Tools;
        }

        return agentChatClient;
    }
}
