// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005

using System;
using System.Threading.Tasks;
using Azure.AI.Agents;

namespace Shared.Foundry;

internal static class AgentFactory
{
    public static async ValueTask<AgentVersion> CreateAgentAsync(
        this AgentsClient agentsClient,
        string agentName,
        PromptAgentDefinition agentDefinition,
        string agentDescription)
    {
        AgentVersionCreationOptions options =
            new()
            {
                Description = agentDescription,
                Metadata =
                    {
                        { "deleteme", bool.TrueString },
                        { "test", bool.TrueString },
                    },
            };

        AgentVersion agentVersion = await agentsClient.CreateAgentVersionAsync(agentName, agentDefinition, options).ConfigureAwait(false);

        Console.ForegroundColor = ConsoleColor.Cyan;
        try
        {
            Console.WriteLine($"PROMPT AGENT: {agentVersion.Name}:{agentVersion.Version}");
        }
        finally
        {
            Console.ResetColor();
        }

        return agentVersion;
    }
}
