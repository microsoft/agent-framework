// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Declarative;

/// <summary>
/// Represents a factory for creating <see cref="AIAgent"/> instances.
/// </summary>
public abstract class AgentFactory
{
    /// <summary>
    /// Gets the types of agents this factory can create.
    /// </summary>
    public IReadOnlyList<string> Types { get; }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFactory"/> class.
    /// </summary>
    /// <param name="types">Types of agent this factory can create</param>
    protected AgentFactory(IEnumerable<string> types)
    {
        this.Types = [.. types];
    }

    /// <summary>
    /// Return true if this instance of <see cref="AgentFactory"/> supports creating agents from the provided <see cref="GptComponentMetadata"/>
    /// </summary>
    /// <param name="agentDefinition">Definition of the agent to check is supported.</param>
    public bool IsSupported(GptComponentMetadata agentDefinition)
    {
        return this.Types.Any(s => string.Equals(s, agentDefinition.GetTypeValue(), StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>
    /// Create a <see cref="AIAgent"/> from the specified <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="agentDefinition">Definition of the agent to create.</param>
    /// <param name="agentCreationOptions">Options used when creating the agent.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <return>The created <see cref="AIAgent"/>, if null the agent type is not supported.</return>
    public async Task<AIAgent> CreateAsync(GptComponentMetadata agentDefinition, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentDefinition);

        var agent = await this.TryCreateAsync(agentDefinition, agentCreationOptions, cancellationToken).ConfigureAwait(false);
        return agent ?? throw new NotSupportedException($"Agent type {agentDefinition.GetTypeValue()} is not supported.");
    }

    /// <summary>
    /// Tries to create a <see cref="AIAgent"/> from the specified <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="agentDefinition">Definition of the agent to create.</param>
    /// <param name="agentCreationOptions">Options used when creating the agent.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <return>The created <see cref="AIAgent"/>, if null the agent type is not supported.</return>
    public abstract Task<AIAgent?> TryCreateAsync(GptComponentMetadata agentDefinition, AgentCreationOptions agentCreationOptions, CancellationToken cancellationToken = default);
}
