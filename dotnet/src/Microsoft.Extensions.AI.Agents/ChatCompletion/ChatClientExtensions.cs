// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents;

internal static class ChatClientExtensions
{
    internal static IChatClient AsAgentInvokingChatClient(this IChatClient chatClient)
    {
        var chatBuilder = chatClient.AsBuilder();

        if (chatClient is not AgentInvokingChatClient agentInvokingChatClient)
        {
            chatBuilder.UseAgentInvocation();
        }

        if (chatClient.GetService<NewFunctionInvokingChatClient>() is null)
        {
            chatBuilder.UseFunctionInvocation();

            chatBuilder.Use((IChatClient innerClient, IServiceProvider services) =>
            {
                var loggerFactory = services.GetService<ILoggerFactory>();

                var newFunctionInvokingChatClient = new NewFunctionInvokingChatClient(innerClient, loggerFactory, services);
                return newFunctionInvokingChatClient;
            });
        }

        if (chatClient.GetService<ApprovalGeneratingChatClient>() is null)
        {
            chatBuilder.Use((IChatClient innerClient, IServiceProvider services) =>
            {
                var loggerFactory = services.GetService<ILoggerFactory>();

                ApprovalGeneratingChatClient approvalGeneratingChatClient = new(innerClient, loggerFactory);
                return approvalGeneratingChatClient;
            });
        }

        return chatBuilder.Build();
    }
}
