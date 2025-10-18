// Copyright (c) Microsoft. All rights reserved.

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
/// and the Microsoft Agent Framework.
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
    /// This method can be used to access A2A agents that support the
    /// <see href="https://github.com/a2aproject/A2A/blob/main/docs/topics/agent-discovery.md#1-well-known-uri">Well-Known URI</see>
    /// discovery mechanism.
    /// </remarks>
    /// <param name="resolver">The <see cref="A2ACardResolver" /> to use for the agent creation.</param>
    /// <param name="httpClient">The <see cref="HttpClient"/> to use for HTTP requests.</param>
    /// <param name="loggerFactory">The logger factory for enabling logging within the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>An <see cref="AIAgent"/> instance backed by the A2A agent.</returns>
    public static async Task<AIAgent> GetAIAgentAsync(this A2ACardResolver resolver, HttpClient? httpClient = null, ILoggerFactory? loggerFactory = null, CancellationToken cancellationToken = default)
    {
        // Obtain the agent card from the resolver.
        var agentCard = await resolver.GetAgentCardAsync(cancellationToken).ConfigureAwait(false);

        return await agentCard.GetAIAgentAsync(httpClient, loggerFactory).ConfigureAwait(false);
    }
}
