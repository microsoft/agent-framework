// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;

internal sealed class VisionAgentProvider(IConfiguration configuration) : AgentProvider(configuration)
{
    protected override async IAsyncEnumerable<AgentVersion> CreateAgentsAsync(Uri foundryEndpoint)
    {
        AIProjectClient aiProjectClient = new(foundryEndpoint, new AzureCliCredential());

        yield return
            await aiProjectClient.CreateAgentAsync(
                agentName: "VisionAgent",
                agentDefinition: this.DefineVisionAgent(),
                agentDescription: "Use computer vision to describe an image or document.");
    }

    private PromptAgentDefinition DefineVisionAgent() =>
        new(this.GetSetting(Settings.FoundryModelFull))
        {
            Instructions =
                """
                Describe the image or document contained in the user request, if any;
                otherwise, suggest that the user provide an image or document.
                """,
        };
}
