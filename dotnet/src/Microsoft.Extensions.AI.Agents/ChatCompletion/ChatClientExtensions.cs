// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents;

internal static class ChatClientExtensions
{
    internal static IChatClient AsAgentInvokedChatClient(this IChatClient chatClient, ChatClientAgentOptions? options)
    {
        var chatBuilder = chatClient.AsBuilder();

        // AgentInvokingChatClient should be the outermost decorator
        if (chatClient is not AgentInvokedChatClient agentInvokingChatClient)
        {
            chatBuilder.UseAgentInvocation();
        }

        if (chatClient.GetService<FunctionInvokingChatClient>() is null && chatClient.GetService<NewFunctionInvokingChatClient>() is null)
        {
            _ = chatBuilder.Use((IChatClient innerClient, IServiceProvider services) =>
            {
                var loggerFactory = services.GetService<ILoggerFactory>();

                return new NewFunctionInvokingChatClient(innerClient, loggerFactory, services);
            });
        }

        var agentChatClient = chatBuilder.Build();

        if (options?.ChatOptions?.Tools is { Count: > 0 })
        {
            // When tools are provided in the constructor, set the tools for the whole lifecycle of the chat client
            var newFunctionService = agentChatClient.GetService<NewFunctionInvokingChatClient>();
            var oldFunctionService = agentChatClient.GetService<FunctionInvokingChatClient>();

            if (newFunctionService is not null)
            {
                newFunctionService.AdditionalTools = options.ChatOptions.Tools;
            }
            else
            {
                oldFunctionService!.AdditionalTools = options.ChatOptions.Tools;
            }
        }

        return agentChatClient;
    }
}
