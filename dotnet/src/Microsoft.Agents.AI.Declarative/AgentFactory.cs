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
    /// Create a <see cref="AIAgent"/> from the specified <see cref="PromptAgent"/>.
    /// </summary>
    /// <param name="promptAgent">Definition of the agent to create.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <return>The created <see cref="AIAgent"/>, if null the agent type is not supported.</return>
    public async Task<AIAgent> CreateAsync(PromptAgent promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var agent = await this.TryCreateAsync(promptAgent, cancellationToken).ConfigureAwait(false);
        return agent ?? throw new NotSupportedException($"Agent type {promptAgent.Kind} is not supported.");
    }

    /// <summary>
    /// Tries to create a <see cref="AIAgent"/> from the specified <see cref="PromptAgent"/>.
    /// </summary>
    /// <param name="promptAgent">Definition of the agent to create.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <return>The created <see cref="AIAgent"/>, if null the agent type is not supported.</return>
    public abstract Task<AIAgent?> TryCreateAsync(PromptAgent promptAgent, CancellationToken cancellationToken = default);
}
