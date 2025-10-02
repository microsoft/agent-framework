// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;

namespace Microsoft.Agents.AI.Hosting;

/// <summary>
/// Provides a catalog of registered AI agents within the hosting environment.
/// </summary>
/// <remarks>
/// The agent catalog allows enumeration of all registered agents in the dependency injection container.
/// This is useful for scenarios where you need to discover and interact with multiple agents programmatically.
/// </remarks>
public abstract class AgentCatalog
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentCatalog"/> class.
    /// </summary>
    protected AgentCatalog()
    {
    }

    /// <summary>
    /// Asynchronously retrieves all registered AI agents from the catalog.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>
    /// An asynchronous enumerable of <see cref="AIAgent"/> instances representing all registered agents.
    /// The enumeration will only include agents that are successfully resolved from the service provider.
    /// </returns>
    /// <remarks>
    /// This method enumerates through all registered agent names and attempts to resolve each agent
    /// from the dependency injection container. Only successfully resolved agents are yielded.
    /// The enumeration is lazy and agents are resolved on-demand during iteration.
    /// </remarks>
    public abstract IAsyncEnumerable<AIAgent> GetAgentsAsync(CancellationToken cancellationToken = default);
}
