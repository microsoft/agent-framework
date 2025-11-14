// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;

internal sealed class PoemAgentProvider(IConfiguration configuration) : AgentProvider(configuration)
{
    protected override async IAsyncEnumerable<AgentVersion> CreateAgentsAsync(Uri foundryEndpoint)
    {
        AIProjectClient aiProjectClient = new(foundryEndpoint, new AzureCliCredential());

        yield return
            await aiProjectClient.CreateAgentAsync(
                agentName: "PoemAgent",
                agentDefinition: this.DefinePoemAgent(),
                agentDescription: "Authors original poems");
    }

    private PromptAgentDefinition DefinePoemAgent() =>
        new(this.GetSetting(Settings.FoundryModelMini))
        {
            Instructions =
                """
                Write a one verse poem on the requested topic in the style of: {{style}}.            
                """,
            StructuredInputs =
            {
                ["style"] =
                    new StructuredInputDefinition
                    {
                        IsRequired = false,
                        DefaultValue = BinaryData.FromString(@"""haiku"""),
                        Description = "The style of poem to write",
                    }
            }
        };
}
