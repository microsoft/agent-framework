// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

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

        if (chatClient.GetService<FunctionInvokingChatClient>() is null)
        {
            chatBuilder.UseFunctionInvocation();
        }

        return chatBuilder.Build();
    }
}
