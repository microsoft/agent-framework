// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.A2A;
using Microsoft.Extensions.Logging;

namespace A2A;

/// <summary>
/// Provides extension methods for <see cref="A2ACardResolver"/>
/// to simplify the creation of A2A agents.
/// </summary>
/// <remarks>
/// These extensions bridge the gap between A2A SDK client objects
/// and the Microsoft Extensions AI Agent framework.
/// <para>
/// They allow developers to easily create AI agents that can interact
/// with A2A agents by handling the conversion from A2A clients to
/// <see cref="A2AAgent"/> instances that implement the <see cref="AIAgent"/> interface.
/// </para>
/// </remarks>
public static class A2ACardResolverExtensions
{
    /// <summary>
    /// Retrieves an instance of <see cref="AIAgent"/> for an existing A2A agent.
    /// </summary>
    /// <remarks>
    /// This method can be used to create AI agents for A2A agents whose hosts support one of the A2A discovery mechanisms:
    /// <list type="bullet">
    /// <item><see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#1-well-known-uri">Well-Known URI</see></item>
    /// <item><see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see></item>
    /// </list>
    /// </remarks>
    /// <param name="resolver">The <see cref="A2ACardResolver" /> to use for the agent creation.</param>
    /// <param name="httpClient">The <see cref="HttpClient"/> to use for HTTP requests.</param>
    /// <param name="loggerFactory">The logger factory for enabling logging within the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to use when retrieving the agent card.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the A2A agent.</returns>
    public static async Task<AIAgent> GetAIAgentAsync(this A2ACardResolver resolver, HttpClient? httpClient = null, ILoggerFactory? loggerFactory = null, CancellationToken cancellationToken = default)
    {
        // Obtain the agent card from the resolver.
        var agentCard = await resolver.GetAgentCardAsync(cancellationToken).ConfigureAwait(false);

        // Create the A2A client using the agent URL from the card.
        var a2aClient = new A2AClient(new Uri(agentCard.Url), httpClient);

        return a2aClient.GetAIAgent(name: agentCard.Name, description: agentCard.Description, loggerFactory: loggerFactory);
    }
}
