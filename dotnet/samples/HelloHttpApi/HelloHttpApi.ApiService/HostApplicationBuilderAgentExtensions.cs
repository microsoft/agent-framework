// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.Orchestration;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;

namespace HelloHttpApi.ApiService;

public static class HostApplicationBuilderAgentExtensions
{
    public static IHostApplicationBuilder AddAIAgent(this IHostApplicationBuilder builder, string name, string instructions, string? chatClientKey = null)
    {
        var agentKey = $"agent:{name}";
        builder.Services.AddKeyedSingleton<AIAgent>(agentKey, (sp, key) =>
        {
            var chatClient = chatClientKey is null ? sp.GetRequiredService<IChatClient>() : sp.GetRequiredKeyedService<IChatClient>(chatClientKey);

            ChatClientAgent triage = new(chatClient, "You are a triage agent. You will determine which agent to hand off the conversation to based on the user's input.", $"{name}_triageAgent");
            ChatClientAgent target = new(chatClient, instructions, $"{name}_targetAgent");
            ChatClientAgent customerService = new(chatClient, "You are a customer service agent. You will handle rude, angry, or upset customer inquiries, asking them to be more calm and polite.", $"{name}_customerServiceAgent");

            return new HandoffOrchestration(OrchestrationHandoffs
                .StartWith(triage)
                .Add(triage, target, "Hand off to the target agent for handling normal customer requests.")
                .Add(triage, customerService, "Hand off to the customer service agent for handling rude customer inquiries."));
        });
        var actorBuilder = builder.AddActorRuntime();

        actorBuilder.AddActorType(
            new ActorType(agentKey),
            (sp, ctx) => new ChatClientAgentActor(
                sp.GetRequiredKeyedService<AIAgent>(agentKey),
                sp.GetService<JsonSerializerOptions>() ?? JsonSerializerOptions.Web,
                ctx,
                sp.GetRequiredService<ILogger<ChatClientAgentActor>>()));

        return builder;
    }
}
