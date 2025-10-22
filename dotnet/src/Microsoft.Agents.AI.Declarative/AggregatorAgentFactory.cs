// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a <see cref="AgentFactory"/> which aggregates multiple agent factories.
/// </summary>
public sealed class AggregatorAgentFactory : AgentFactory
{
    private readonly AgentFactory[] _agentFactories;

    /// <summary>Initializes the instance.</summary>
    /// <param name="agentFactories">Ordered <see cref="AgentFactory"/> instances to aggregate.</param>
    /// <remarks>
    /// Where multiple <see cref="AgentFactory"/> instances are provided, the first factory that supports the <see cref="PromptAgent"/> will be used.
    /// </remarks>
    public AggregatorAgentFactory(params AgentFactory[] agentFactories)
    {
        Throw.IfNullOrEmpty(agentFactories);

        foreach (AgentFactory agentFactory in agentFactories)
        {
            Throw.IfNull(agentFactory, nameof(agentFactories));
        }

        this._agentFactories = agentFactories;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(PromptAgent promptAgent, AgentCreationOptions? agentCreationOptions = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        foreach (var agentFactory in this._agentFactories)
        {
            var agent = await agentFactory.TryCreateAsync(promptAgent, agentCreationOptions, cancellationToken).ConfigureAwait(false);
            if (agent is not null)
            {
                return agent;
            }
        }

        return null;
    }
}
