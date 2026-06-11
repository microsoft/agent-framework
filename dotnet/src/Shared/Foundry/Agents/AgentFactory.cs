// Copyright (c) Microsoft. All rights reserved.

#pragma warning disable IDE0005

using System;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Azure.AI.Projects.Agents;

namespace Shared.Foundry;

internal static class AgentFactory
{
    public static async ValueTask<ProjectsAgentVersion> CreateAgentAsync(
        this AIProjectClient aiProjectClient,
        string agentName,
        ProjectsAgentDefinition agentDefinition,
        string agentDescription)
    {
        ProjectsAgentVersionCreationOptions options =
            new(agentDefinition)
            {
                Description = agentDescription,
                Metadata =
                    {
                        { "deleteme", bool.TrueString },
                        { "test", bool.TrueString },
                    },
            };

        ProjectsAgentVersion agentVersion = await aiProjectClient.AgentAdministrationClient.CreateAgentVersionAsync(agentName, options).ConfigureAwait(false);

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
