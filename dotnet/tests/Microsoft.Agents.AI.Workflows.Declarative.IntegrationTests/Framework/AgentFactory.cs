// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Frozen;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.SemanticKernel;
using Microsoft.SemanticKernel.Agents;
using Microsoft.SemanticKernel.Agents.AzureAI;
using Shared.IntegrationTests;

namespace Microsoft.Agents.AI.Workflows.Declarative.IntegrationTests.Framework;

internal static class AgentFactory
{
    private static readonly Dictionary<string, string> s_agentDefinitions =
        new()
        {
            ["FOUNDRY_AGENT_TEST"] = "TestAgent.yaml",
            ["FOUNDRY_AGENT_TOOL"] = "ToolAgent.yaml",
            ["FOUNDRY_AGENT_ANSWER"] = "QuestionAgent.yaml",
            ["FOUNDRY_AGENT_STUDENT"] = "StudentAgent.yaml",
            ["FOUNDRY_AGENT_TEACHER"] = "TeacherAgent.yaml",
            ["FOUNDRY_AGENT_RESEARCHANALYST"] = "AnalystAgent.yaml",
            ["FOUNDRY_AGENT_RESEARCHCODER"] = "CoderAgent.yaml",
            ["FOUNDRY_AGENT_RESEARCHMANAGER"] = "ManagerAgent.yaml",
            ["FOUNDRY_AGENT_RESEARCHWEATHER"] = "WeatherAgent.yaml",
            ["FOUNDRY_AGENT_RESEARCHWEB"] = "WebAgent.yaml",
        };

    private static FrozenDictionary<string, string?>? s_agentMap;

    public static async Task<FrozenDictionary<string, string?>> GetAgentsAsync(AzureAIConfiguration config, IConfiguration configuration, CancellationToken cancellationToken = default)
    {
        if (s_agentMap is not null)
        {
            return s_agentMap;
        }

        PersistentAgentsClient clientAgents = new(config.Endpoint, new AzureCliCredential());
        AIProjectClient clientProjects = new(new Uri(config.Endpoint), new AzureCliCredential());
        IKernelBuilder kernelBuilder = Kernel.CreateBuilder();
        kernelBuilder.Services.AddSingleton(clientAgents);
        kernelBuilder.Services.AddSingleton(clientProjects);
        kernelBuilder.Plugins.AddFromType<Agents.MenuPlugin>();
        AgentCreationOptions creationOptions = new() { Kernel = kernelBuilder.Build() };
        AzureAIAgentFactory factory = new();
        string repoRoot = WorkflowTest.GetRepoFolder();

        return s_agentMap = (await Task.WhenAll(s_agentDefinitions.Select(kvp => CreateAgentAsync(kvp.Key, kvp.Value, cancellationToken)))).ToFrozenDictionary(t => t.Name, t => t.Id);

        async Task<(string Name, string? Id)> CreateAgentAsync(string id, string file, CancellationToken cancellationToken)
        {
            try
            {
                string filePath = Path.Combine(Environment.CurrentDirectory, "Agents", file);
                if (!File.Exists(filePath))
                {
                    filePath = Path.Combine(repoRoot, "workflow-samples", "setup", file);
                }
                Assert.True(File.Exists(filePath), $"Agent definition file not found: {file}");

                Debug.WriteLine($"TEST AGENT: Creating - {file}");
                string agentText = File.ReadAllText(filePath);

                Agent? agent = await factory.CreateAgentFromYamlAsync(agentText, creationOptions, configuration, cancellationToken);

                Assert.NotNull(agent?.Name);

                Debug.WriteLine($"TEST AGENT: {agent.Name} => {agent.Id} [{id}]");

                return (id, agent.Id);
            }
            catch (Exception exception)
            {
                Console.WriteLine($"FAILURE: Error creating agent {id}: {exception.Message}");
                throw;
            }
        }
    }
}
