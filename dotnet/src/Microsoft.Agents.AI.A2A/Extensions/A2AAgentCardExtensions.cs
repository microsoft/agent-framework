// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.Logging;

namespace A2A;

/// <summary>
/// Provides extension methods for <see cref="AgentCard"/> to simplify the creation of A2A agents.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between A2A SDK client <see cref="AgentCard"/> and <see cref="AIAgent"/>.
/// </remarks>
public static class A2AAgentCardExtensions
{
    /// <summary>
    /// Retrieves an instance of <see cref="AIAgent"/> for an existing A2A agent.
    /// </summary>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism.
    /// </remarks>
    /// <param name="card">The <see cref="AgentCard" /> to use for the agent creation.</param>
    /// <param name="httpClient">The <see cref="HttpClient"/> to use for HTTP requests.</param>
    /// <param name="loggerFactory">The logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the A2A agent.</returns>
    public static async Task<AIAgent> GetAIAgentAsync(this AgentCard card, HttpClient? httpClient = null, ILoggerFactory? loggerFactory = null)
    {
        // Create the A2A client using the agent URL from the card.
        var a2aClient = new A2AClient(new Uri(card.Url), httpClient);

        return a2aClient.GetAIAgent(name: card.Name, description: card.Description, loggerFactory: loggerFactory);
    }
}
