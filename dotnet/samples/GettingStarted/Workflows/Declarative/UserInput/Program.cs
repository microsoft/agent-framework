// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;
using Shared.Workflows;

namespace Demo.Agents.MathChat;

internal sealed class Program
{
    public static async Task Main(string[] args)
    {
        IConfiguration configuration = Application.InitializeConfig();
        string foundryEndpoint = configuration.GetValue(Application.Settings.FoundryEndpoint);
        AgentsClient agentsClient = new(new Uri(foundryEndpoint), new AzureCliCredential());

        await agentsClient.CreateAgentAsync(
            agentName: "ServiceAgent",
            agentDefinition: DefineServiceAgent(configuration),
            agentDescription: "Service agent for UserInput workflow");

        await agentsClient.CreateAgentAsync(
            agentName: "IntentAgent",
            agentDefinition: DefineIntentAgent(configuration),
            agentDescription: "Intent agent for UserInput workflow");
    }

    private static PromptAgentDefinition DefineServiceAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Interact with the user to gather necessary and complete information related to
                what they want to talk about.
                """
        };

    private static PromptAgentDefinition DefineIntentAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelMini))
        {
            Instructions =
                """
                Describe the user's full intent based on the conversation.
                """
        };
}
