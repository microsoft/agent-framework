// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Identity;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
using Microsoft.SemanticKernel.Agents.AzureAI;
using Shared.IntegrationTests;

namespace Microsoft.Agents.Workflows.Declarative.IntegrationTests.Framework;

#pragma warning disable SKEXP0110 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

internal static class AgentFactory
{
    public static async Task<IReadOnlyDictionary<string, string?>> CreateAsync(string agentsDirectory, AzureAIConfiguration config, CancellationToken cancellationToken)
    {
        PersistentAgentsClient clientAgents = new(config.Endpoint, new AzureCliCredential());

        IKernelBuilder kernelBuilder = Kernel.CreateBuilder();
        kernelBuilder.Services.AddSingleton(clientAgents);
        Kernel kernel = kernelBuilder.Build();

        AzureAIAgentFactory factory = new();

        Dictionary<string, string?> agentMap = [];

        foreach (string file in Directory.GetFiles(agentsDirectory, "*.yaml"))
        {
            Debug.WriteLine($"TEST AGENT: Creating - {file}");
            string agentText = File.ReadAllText(file);

            Agent? agent = await factory.CreateAgentFromYamlAsync(agentText, new AgentCreationOptions() { Kernel = kernel }, configuration: null, cancellationToken);

            Assert.NotNull(agent?.Name);

            Debug.WriteLine($"TEST AGENT: {agent.Name} => {agent.Id}");
            agentMap[agent.Name] = agent.Id;
        }

        return agentMap;
    }
}
