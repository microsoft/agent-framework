// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a <see cref="PromptAgentFactory"/> which aggregates multiple agent factories.
/// </summary>
public sealed class AggregatorPromptAgentFactory : PromptAgentFactory
{
    private readonly PromptAgentFactory[] _agentFactories;

    /// <summary>Initializes the instance.</summary>
    /// <param name="agentFactories">Ordered <see cref="PromptAgentFactory"/> instances to aggregate.</param>
    /// <remarks>
    /// Where multiple <see cref="PromptAgentFactory"/> instances are provided, the first factory that supports the <see cref="GptComponentMetadata"/> will be used.
    /// </remarks>
    public AggregatorPromptAgentFactory(params PromptAgentFactory[] agentFactories)
    {
        Throw.IfNullOrEmpty(agentFactories);

        foreach (PromptAgentFactory agentFactory in agentFactories)
        {
            Throw.IfNull(agentFactory, nameof(agentFactories));
        }

        this._agentFactories = agentFactories;
    }

    /// <inheritdoc/>
    public override async Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        foreach (var agentFactory in this._agentFactories)
        {
            var agent = await agentFactory.TryCreateAsync(promptAgent, cancellationToken).ConfigureAwait(false);
            if (agent is not null)
            {
                return agent;
            }
        }

        return null;
    }
}
