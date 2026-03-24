// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
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
    /// <param name="interfaceSelector">
    /// An optional callback to select which <see cref="AgentInterface"/> to use from the card's
    /// <see cref="AgentCard.SupportedInterfaces"/>. When not provided, the first interface is used.
    /// </param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the A2A agent.</returns>
    public static AIAgent AsAIAgent(this AgentCard card, HttpClient? httpClient = null, ILoggerFactory? loggerFactory = null, Func<IReadOnlyList<AgentInterface>, AgentInterface>? interfaceSelector = null)
    {
        var interfaces = card.SupportedInterfaces
            ?? throw new InvalidOperationException("The AgentCard does not have any SupportedInterfaces.");

        // Use the provided selector or default to the first interface.
        var selectedInterface = interfaceSelector is not null
            ? interfaceSelector(interfaces)
            : interfaces.FirstOrDefault()
                ?? throw new InvalidOperationException("The AgentCard does not have any SupportedInterfaces with a URL.");

        var url = selectedInterface.Url
            ?? throw new InvalidOperationException("The selected AgentInterface does not have a URL.");

        // Create the A2A client using the agent URL from the card.
        var a2aClient = new A2AClient(new Uri(url), httpClient);

        return a2aClient.AsAIAgent(name: card.Name, description: card.Description, loggerFactory: loggerFactory);
    }
}
