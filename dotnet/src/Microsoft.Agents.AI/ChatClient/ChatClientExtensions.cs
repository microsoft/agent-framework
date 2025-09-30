// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI;

internal static class ChatClientExtensions
{
    internal static IChatClient WithDefaultAgentMiddleware(this IChatClient chatClient, ChatClientAgentOptions? options, IServiceProvider? functionInvocationServices = null)
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

        var agentChatClient = chatBuilder.Build(functionInvocationServices);

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
