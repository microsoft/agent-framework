// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents.Hosting.Builders;
using Microsoft.Extensions.AI.Agents.Hosting.Discovery.Model;

namespace Microsoft.Extensions.AI.Agents.Hosting.Discovery.Internal;

internal static class AgentHostingBuilderExtensions
{
    public static AgentMetadata ResolveAgentMetadata(this IAgentHostingBuilder builder)
    {
        return builder switch
        {
            ChatClientAgentHostingBuilder chatClientBuilder => ResolveChatClientAgentMetadata(chatClientBuilder),
            _ => new AgentMetadata(builder.ActorType)
        };
    }

    private static AgentMetadata ResolveChatClientAgentMetadata(ChatClientAgentHostingBuilder builder)
        => new(builder.ActorType)
        {
            Description = builder.Description,
            Instructions = builder.Instructions
        };
}
