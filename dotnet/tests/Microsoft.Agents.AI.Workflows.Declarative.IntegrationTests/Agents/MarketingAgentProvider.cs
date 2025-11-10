// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Azure.AI.Agents;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Shared.Foundry;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;

internal sealed class MarketingAgentProvider(IConfiguration configuration) : AgentProvider(configuration)
{
    protected override async IAsyncEnumerable<AgentVersion> CreateAgentsAsync(Uri foundryEndpoint)
    {
        AgentClient agentClient = new(foundryEndpoint, new AzureCliCredential());

        yield return
            await agentClient.CreateAgentAsync(
                agentName: "AnalystAgent",
                agentDefinition: this.DefineAnalystAgent(),
                agentDescription: "Analyst agent for Marketing workflow");

        yield return
            await agentClient.CreateAgentAsync(
                agentName: "WriterAgent",
                agentDefinition: this.DefineWriterAgent(),
                agentDescription: "Writer agent for Marketing workflow");

        yield return
            await agentClient.CreateAgentAsync(
                agentName: "EditorAgent",
                agentDefinition: this.DefineEditorAgent(),
                agentDescription: "Editor agent for Marketing workflow");
    }

    private PromptAgentDefinition DefineAnalystAgent() =>
        new(this.GetSetting(Settings.FoundryModelFull))
        {
            Instructions =
                """
                You are a marketing analyst. Given a product description, identify:
                - Key features
                - Target audience
                - Unique selling points
                """,
            Tools =
            {
                //AgentTool.CreateBingGroundingTool( // TODO: Use Bing Grounding when available
                //    new BingGroundingSearchToolParameters(
                //        [new BingGroundingSearchConfiguration(this.GetSetting(Settings.FoundryGroundingTool))]))
            }
        };

    private PromptAgentDefinition DefineWriterAgent() =>
        new(this.GetSetting(Settings.FoundryModelFull))
        {
            Instructions =
                """
                You are a marketing copywriter. Given a block of text describing features, audience, and USPs,
                compose a compelling marketing copy (like a newsletter section) that highlights these points.
                Output should be short (around 150 words), output just the copy as a single text block.
                """
        };

    private PromptAgentDefinition DefineEditorAgent() =>
        new(this.GetSetting(Settings.FoundryModelFull))
        {
            Instructions =
                """
                You are an editor. Given the draft copy, correct grammar, improve clarity, ensure consistent tone,
                give format and make it polished. Output the final improved copy as a single text block.
                """
        };
}
