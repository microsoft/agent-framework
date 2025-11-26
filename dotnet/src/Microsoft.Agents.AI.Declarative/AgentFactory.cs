// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.Configuration;
using Microsoft.PowerFx;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a factory for creating <see cref="AIAgent"/> instances.
/// </summary>
public abstract class AgentFactory
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFactory"/> class.
    /// </summary>
    /// <param name="configuration">The configuration.</param>
    protected AgentFactory(IConfiguration? configuration = null)
    {
        this.Engine = new RecalcEngine();

        if (configuration is not null)
        {
            foreach (var kvp in configuration.AsEnumerable())
            {
                this.Engine.UpdateVariable(kvp.Key, kvp.Value ?? string.Empty);
            }
        }
    }

    /// <summary>
    /// Gets the Power Fx recalculation engine used to evaluate expressions in agent definitions.
    /// This engine is configured with variables from the <see cref="IConfiguration"/> provided during construction.
    /// </summary>
    protected RecalcEngine Engine { get; }

    /// <summary>
    /// Create a <see cref="AIAgent"/> from the specified <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="promptAgent">Definition of the agent to create.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <return>The created <see cref="AIAgent"/>, if null the agent type is not supported.</return>
    public async Task<AIAgent> CreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var agent = await this.TryCreateAsync(promptAgent, cancellationToken).ConfigureAwait(false);
        return agent ?? throw new NotSupportedException($"Agent type {promptAgent.Kind} is not supported.");
    }

    /// <summary>
    /// Tries to create a <see cref="AIAgent"/> from the specified <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="promptAgent">Definition of the agent to create.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <return>The created <see cref="AIAgent"/>, if null the agent type is not supported.</return>
    public abstract Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default);
}
