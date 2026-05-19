// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.A2A;
using Microsoft.Extensions.Logging;
using Microsoft.Shared.Diagnostics;

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
    /// <param name="options">
    /// Optional <see cref="A2AClientOptions"/> controlling protocol binding preference.
    /// When not provided, defaults to preferring HTTP+JSON first, with JSON-RPC as fallback.
    /// </param>
    /// <param name="loggerFactory">The logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the A2A agent.</returns>
    public static AIAgent AsAIAgent(this AgentCard card, HttpClient? httpClient = null, A2AClientOptions? options = null, ILoggerFactory? loggerFactory = null)
    {
        var a2aClient = A2AClientFactory.Create(card, httpClient, options);

        return a2aClient.AsAIAgent(name: card.Name, description: card.Description, loggerFactory: loggerFactory);
    }

    /// <summary>
    /// Retrieves an instance of <see cref="AIAgent"/> for an existing A2A agent.
    /// </summary>
    /// <remarks>
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#2-curated-registries-catalog-based-discovery">Curated Registries (Catalog-Based Discovery)</see>
    /// discovery mechanism. When <paramref name="agentOptions"/> is provided, any non-null values override
    /// the corresponding values from the <see cref="AgentCard"/>.
    /// </remarks>
    /// <param name="card">The <see cref="AgentCard" /> to use for the agent creation.</param>
    /// <param name="agentOptions">
    /// Configuration options that control the agent's identity. When provided, non-null values override the
    /// corresponding values from the agent card.
    /// </param>
    /// <param name="httpClient">The <see cref="HttpClient"/> to use for HTTP requests.</param>
    /// <param name="clientOptions">
    /// Optional <see cref="A2AClientOptions"/> controlling protocol binding preference.
    /// When not provided, defaults to preferring HTTP+JSON first, with JSON-RPC as fallback.
    /// </param>
    /// <param name="loggerFactory">The logger factory for enabling logging within the agent.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the A2A agent.</returns>
    public static AIAgent AsAIAgent(this AgentCard card, A2AAgentOptions agentOptions, HttpClient? httpClient = null, A2AClientOptions? clientOptions = null, ILoggerFactory? loggerFactory = null)
    {
        _ = Throw.IfNull(card);
        _ = Throw.IfNull(agentOptions);

        var a2aClient = A2AClientFactory.Create(card, httpClient, clientOptions);

        var mergedOptions = agentOptions.Clone();
        mergedOptions.Name ??= card.Name;
        mergedOptions.Description ??= card.Description;

        return a2aClient.AsAIAgent(mergedOptions, loggerFactory);
    }
}
