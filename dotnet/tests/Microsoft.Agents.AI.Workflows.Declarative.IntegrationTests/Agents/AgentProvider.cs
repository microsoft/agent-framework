// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Azure.AI.Projects.OpenAI;
using Microsoft.Extensions.Configuration;
using Shared.IntegrationTests;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Agents;

internal abstract class AgentProvider(IConfiguration configuration)
{
    public static class Names
    {
        public const string FunctionTool = "FUNCTIONTOOL";
        public const string Marketing = "MARKETING";
        public const string MathChat = "MATHCHAT";
        public const string InputArguments = "INPUTARGUMENTS";
        public const string Vision = "VISION";
    }

    public static AgentProvider Create(IConfiguration configuration, string providerType) =>
        providerType.ToUpperInvariant() switch
        {
            Names.FunctionTool => new FunctionToolAgentProvider(configuration),
            Names.Marketing => new MarketingAgentProvider(configuration),
            Names.MathChat => new MathChatAgentProvider(configuration),
            Names.InputArguments => new PoemAgentProvider(configuration),
            Names.Vision => new VisionAgentProvider(configuration),
            _ => new TestAgentProvider(configuration),
        };

    public async ValueTask CreateAgentsAsync()
    {
        Uri foundryEndpoint = new(this.GetSetting(TestSettings.AzureAIProjectEndpoint));

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
