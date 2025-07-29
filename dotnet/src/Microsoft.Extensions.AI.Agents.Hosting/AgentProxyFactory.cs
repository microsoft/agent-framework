// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents.Hosting;

/// <summary>
/// Factory class for creating instances of <see cref="AgentProxy"/>.
/// </summary>
public sealed class AgentProxyFactory
{
    private readonly IActorClient _client;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentProxyFactory"/> class.
    /// </summary>
    /// <param name="client">The actor client.</param>
    public AgentProxyFactory(IActorClient client)
    {
        Throw.IfNull(client);
        this._client = client;
    }

    /// <summary>
    /// Creates a new <see cref="AgentProxy"/> instance with the specified agent name.
    /// </summary>
    /// <param name="name">The name of the agent.</param>
    /// <returns>A new <see cref="AgentProxy"/> instance.</returns>
    public AgentProxy Create(string name)
    {
        Throw.IfNullOrEmpty(name);
        return new AgentProxy(name, this._client);
    }
}
