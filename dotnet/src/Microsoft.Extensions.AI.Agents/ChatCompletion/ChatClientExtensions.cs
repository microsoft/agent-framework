// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
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

        if (chatClient.GetService<FunctionInvokingChatClient>() is null)
        {
            _ = chatBuilder.Use((innerClient, services) =>
            {
                var loggerFactory = services.GetService<ILoggerFactory>();

                return new FunctionInvokingChatClient(innerClient, loggerFactory, services);
            });
        }

        var agentChatClient = chatBuilder.Build();

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
