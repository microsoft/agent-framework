// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a factory for creating <see cref="AIAgent"/> instances.
/// </summary>
public abstract class AgentFactory
{
    /// <summary>
    /// Return true if this instance of <see cref="AgentFactory"/> supports creating agents from the provided <see cref="PromptAgent"/>
    /// </summary>
    /// <param name="promptAgent">Definition of the agent to check is supported.</param>
    public bool IsSupported(PromptAgent promptAgent)
    {
        // TODO: Make this abstract and implement in derived classes
        return true;
    }

    /// <summary>
    /// Create a <see cref="AIAgent"/> from the specified <see cref="PromptAgent"/>.
    /// </summary>
    /// <param name="promptAgent">Definition of the agent to create.</param>
    /// <param name="agentCreationOptions">Options used when creating the agent.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <return>The created <see cref="AIAgent"/>, if null the agent type is not supported.</return>
    public async Task<AIAgent> CreateAsync(PromptAgent promptAgent, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var agent = await this.TryCreateAsync(promptAgent, agentCreationOptions, cancellationToken).ConfigureAwait(false);
        return agent ?? throw new NotSupportedException($"Agent type {promptAgent.Kind} is not supported.");
    }

    /// <summary>
    /// Tries to create a <see cref="AIAgent"/> from the specified <see cref="PromptAgent"/>.
    /// </summary>
    /// <param name="promptAgent">Definition of the agent to create.</param>
    /// <param name="agentCreationOptions">Options used when creating the agent.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <return>The created <see cref="AIAgent"/>, if null the agent type is not supported.</return>
    public abstract Task<AIAgent?> TryCreateAsync(PromptAgent promptAgent, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default);
}
