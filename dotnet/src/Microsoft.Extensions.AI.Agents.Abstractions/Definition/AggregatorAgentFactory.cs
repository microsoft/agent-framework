// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Provides a <see cref="AgentFactory"/> which aggregates multiple agent factories.
/// </summary>
public sealed class AggregatorAgentFactory : AgentFactory
{
    private readonly AgentFactory[] _agentFactories;

    /// <summary>Initializes the instance.</summary>
    /// <param name="agentFactories">Ordered <see cref="AgentFactory"/> instances to aggregate.</param>
    /// <remarks>
    /// Where multiple <see cref="AgentFactory"/> instances are provided, the first factory that supports the <see cref="AgentDefinition"/> will be used.
    /// </remarks>
    public AggregatorAgentFactory(params AgentFactory[] agentFactories) : base(agentFactories.SelectMany(f => f.Types).ToArray())
    {
        Throw.IfNullOrEmpty(agentFactories);

        foreach (AgentFactory agentFactory in agentFactories)
        {
            Throw.IfNull(agentFactory);
        }

        this._agentFactories = agentFactories;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(AgentDefinition agentDefinition, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentDefinition);

        foreach (var agentFactory in this._agentFactories)
        {
            if (agentFactory.IsSupported(agentDefinition))
            {
                var kernelAgent = await agentFactory.TryCreateAsync(agentDefinition, agentCreationOptions, cancellationToken).ConfigureAwait(false);
                if (kernelAgent is not null)
                {
                    return kernelAgent;
                }
            }
        }

        return null;
    }
}
