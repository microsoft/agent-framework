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

        if (chatClient.GetService<FunctionInvokingChatClient>() is null)
        {
            _ = chatBuilder.Use((innerClient, services) =>
            {
                var loggerFactory = services.GetService<ILoggerFactory>();

                return new FunctionInvokingChatClient(innerClient, loggerFactory, services);
            });
        }

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
