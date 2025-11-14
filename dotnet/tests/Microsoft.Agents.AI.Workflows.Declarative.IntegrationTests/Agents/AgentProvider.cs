// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Azure.AI.Projects.OpenAI;
using Microsoft.Extensions.Configuration;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;

internal abstract class AgentProvider(IConfiguration configuration)
{
    public static class Names
    {
        public const string FunctionTool = "FUNCTIONTOOL";
        public const string Marketing = "MARKETING";
        public const string MathChat = "MATHCHAT";
        public const string InputArguments = "INPUTARGUMENTS";
    }

    public static class Settings
    {
        public const string FoundryEndpoint = "FOUNDRY_PROJECT_ENDPOINT";
        public const string FoundryModelMini = "FOUNDRY_MODEL_DEPLOYMENT_NAME";
        public const string FoundryModelFull = "FOUNDRY_MEDIA_DEPLOYMENT_NAME";
        public const string FoundryGroundingTool = "FOUNDRY_CONNECTION_GROUNDING_TOOL";
    }

    public static AgentProvider Create(IConfiguration configuration, string providerType) =>
        providerType.ToUpperInvariant() switch
        {
            Names.FunctionTool => new FunctionToolAgentProvider(configuration),
            Names.Marketing => new MarketingAgentProvider(configuration),
            Names.MathChat => new MathChatAgentProvider(configuration),
            Names.InputArguments => new PoemAgentProvider(configuration),
            _ => new TestAgentProvider(configuration),
        };

    public async ValueTask CreateAgentsAsync()
    {
        Uri foundryEndpoint = new(this.GetSetting(Settings.FoundryEndpoint));

        await foreach (AgentVersion agent in this.CreateAgentsAsync(foundryEndpoint))
        {
            Console.WriteLine($"Created agent: {agent.Name}:{agent.Version}");
        }
    }

    protected abstract IAsyncEnumerable<AgentVersion> CreateAgentsAsync(Uri foundryEndpoint);

    protected string GetSetting(string settingName) =>
        configuration[settingName] ??
        throw new InvalidOperationException($"Undefined configuration setting: {settingName}");
}
