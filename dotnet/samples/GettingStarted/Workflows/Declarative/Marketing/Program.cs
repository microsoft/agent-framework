// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Agents;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using OpenAI.Responses;
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
            agentName: "AnalystAgent",
            agentDefinition: DefineAnalystAgent(configuration),
            agentDescription: "Analyst agent for Marketing workflow");

        await agentsClient.CreateAgentAsync(
            agentName: "WriterAgent",
            agentDefinition: DefineWriterAgent(configuration),
            agentDescription: "Writer agent for Marketing workflow");

        await agentsClient.CreateAgentAsync(
            agentName: "EditorAgent",
            agentDefinition: DefineEditorAgent(configuration),
            agentDescription: "Editor agent for Marketing workflow");
    }

    private static PromptAgentDefinition DefineAnalystAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelFull))
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
                AgentTool.CreateBingGroundingTool(
                    new BingGroundingSearchToolParameters(
                        [new BingGroundingSearchConfiguration(configuration[Application.Settings.FoundryGroundingTool])]))
            }
        };

    private static PromptAgentDefinition DefineWriterAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelFull))
        {
            Instructions =
                """
                You are a marketing copywriter. Given a block of text describing features, audience, and USPs,
                compose a compelling marketing copy (like a newsletter section) that highlights these points.
                Output should be short (around 150 words), output just the copy as a single text block.
                """
        };

    private static PromptAgentDefinition DefineEditorAgent(IConfiguration configuration) =>
        new(configuration.GetValue(Application.Settings.FoundryModelFull))
        {
            Instructions =
                """
                You are an editor. Given the draft copy, correct grammar, improve clarity, ensure consistent tone,
                give format and make it polished. Output the final improved copy as a single text block.
                """
        };
}
