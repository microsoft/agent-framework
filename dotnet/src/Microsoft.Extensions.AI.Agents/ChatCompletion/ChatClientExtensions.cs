// Copyright (c) Microsoft. All rights reserved.

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
        }

        return chatBuilder.Build();
    }
}
