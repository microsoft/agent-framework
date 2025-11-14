// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
using Shared.Foundry;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;

internal sealed class FunctionToolAgentProvider(IConfiguration configuration) : AgentProvider(configuration)
{
    protected override async IAsyncEnumerable<AgentVersion> CreateAgentsAsync(Uri foundryEndpoint)
    {
        MenuPlugin menuPlugin = new();
        AIFunction[] functions =
            [
                AIFunctionFactory.Create(menuPlugin.GetMenu),
                AIFunctionFactory.Create(menuPlugin.GetSpecials),
                AIFunctionFactory.Create(menuPlugin.GetItemPrice),
            ];

        AIProjectClient aiProjectClient = new(foundryEndpoint, new AzureCliCredential());

        yield return
            await aiProjectClient.CreateAgentAsync(
                agentName: "MenuAgent",
                agentDefinition: this.DefineMenuAgent(functions),
                agentDescription: "Provides information about the restaurant menu");
    }

    private PromptAgentDefinition DefineMenuAgent(AIFunction[] functions)
    {
        PromptAgentDefinition agentDefinition =
            new(this.GetSetting(Settings.FoundryModelMini))
            {
                Instructions =
                    """
                    Answer the users questions on the menu.
                    For questions or input that do not require searching the documentation, inform the
                    user that you can only answer questions what's on the menu.
                    """
            };

        foreach (AIFunction function in functions)
        {
            agentDefinition.Tools.Add(function.AsOpenAIResponseTool());
        }

        return agentDefinition;
    }
}
