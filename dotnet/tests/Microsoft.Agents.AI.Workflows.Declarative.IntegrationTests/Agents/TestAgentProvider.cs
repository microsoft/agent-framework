// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;

internal sealed class TestAgentProvider(IConfiguration configuration) : AgentProvider(configuration)
{
    protected override async IAsyncEnumerable<AgentVersion> CreateAgentsAsync(Uri foundryEndpoint)
    {
        AIProjectClient aiProjectClient = new(foundryEndpoint, new AzureCliCredential());

        yield return
            await aiProjectClient.CreateAgentAsync(
                agentName: "TestAgent",
                agentDefinition: this.DefineMenuAgent(),
                agentDescription: "Provides information about the restaurant menu");
    }

    private PromptAgentDefinition DefineMenuAgent() =>
        new(this.GetSetting(Settings.FoundryModelFull));
}
