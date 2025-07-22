// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace HelloHttpApi.ApiService;

public static class HostApplicationBuilderAgentExtensions
{
    public static IHostApplicationBuilder AddChatClientAgent(this IHostApplicationBuilder builder, string name, string instructions, string? chatClientKey = null)
    {
        var agentKey = $"agent:{name}";
        builder.Services.AddKeyedSingleton(agentKey, (sp, key) =>
        {
            var chatClient = chatClientKey is null ? sp.GetRequiredService<IChatClient>() : sp.GetRequiredKeyedService<IChatClient>(chatClientKey);
            return new ChatClientAgent(chatClient, instructions, name);
        });
        var actorBuilder = builder.AddActorRuntime();

        actorBuilder.AddActorType(
            new ActorType(agentKey),
            (sp, ctx) => new ChatClientAgentActor(
                sp.GetRequiredKeyedService<ChatClientAgent>(agentKey),
                sp.GetService<JsonSerializerOptions>() ?? JsonSerializerOptions.Web,
                ctx,
                sp.GetRequiredService<ILogger<ChatClientAgentActor>>()));

        return builder;
    }
}
