// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.Logging;
using OpenAI.Chat;
using OpenAI.Responses;

namespace OpenAI;

/// <summary>
/// Extension methods for <see cref="OpenAIClient"/>.
/// </summary>
internal static class OpenAIClientExtensions
{
    internal static AIAgent GetChatClientAgent(this OpenAIClient client, string model, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        var chatClient = client.GetChatClient(model).AsIChatClient();
        ChatClientAgent agent = new(chatClient, instructions, name, description, tools, loggerFactory);
        return agent;
    }

    internal static AIAgent GetAgent(this ChatClient client, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        var chatClient = client.AsIChatClient();
        ChatClientAgent agent = new(chatClient, instructions, name, description, tools, loggerFactory);
        return agent;
    }

    internal static AIAgent GetOpenAIResponseClientAgent(this OpenAIClient client, string model, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        var chatClient = client.GetOpenAIResponseClient(model).AsIChatClient();
        ChatClientAgent agent = new(chatClient, instructions, name, description, tools, loggerFactory);
        return agent;
    }

    internal static AIAgent GetAgent(this OpenAIResponseClient client, string? instructions = null, string? name = null, string? description = null, IList<AITool>? tools = null, ILoggerFactory? loggerFactory = null)
    {
        var chatClient = client.AsIChatClient();
        ChatClientAgent agent = new(chatClient, instructions, name, description, tools, loggerFactory);
        return agent;
    }
}
