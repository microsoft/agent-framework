// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005

using System;
using System.Threading.Tasks;
using Azure.AI.Agents;

namespace Shared.Foundry;

internal static class AgentFactory
{
    public static async ValueTask<AgentVersion> CreateAgentAsync(
        this AgentClient agentClient,
        string agentName,
        AgentDefinition agentDefinition,
        string agentDescription)
    {
        AgentVersionCreationOptions options =
            new(agentDefinition)
            {
                Description = agentDescription,
                Metadata =
                    {
                        { "deleteme", bool.TrueString },
                        { "test", bool.TrueString },
                    },
            };

        AgentVersion agentVersion = await agentClient.CreateAgentVersionAsync(agentName, options).ConfigureAwait(false);

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
