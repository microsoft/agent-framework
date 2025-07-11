// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Provides extension methods for the agent runtime.
/// </summary>
public static class AgentRuntimeExtensions
{
    /// <summary>
    /// Retrieves an actor by its type.
    /// </summary>
    /// <param name="agentRuntime">The agent runtime.</param>
    /// <param name="actorType">The type of the actor.</param>
    /// <param name="key">An optional key to specify variations of the actor. Defaults to "default".</param>
    /// <param name="lazy">If <c>true</c>, the actor is fetched lazily.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation, returning the actor's ID.</returns>
    public static ValueTask<ActorId> GetActorAsync(this IAgentRuntime agentRuntime, ActorType actorType, string? key = null, bool lazy = true, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentRuntime);

        return agentRuntime.GetActorAsync(actorType.Name, key, lazy, cancellationToken);
    }

    /// <summary>
    /// Retrieves an actor by its string representation.
    /// </summary>
    /// <param name="agentRuntime">The agent runtime.</param>
    /// <param name="actor">The string representation of the actor.</param>
    /// <param name="key">An optional key to specify variations of the actor. Defaults to "default".</param>
    /// <param name="lazy">If <c>true</c>, the actor is fetched lazily.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation, returning the actor's ID.</returns>
    public static ValueTask<ActorId> GetActorAsync(this IAgentRuntime agentRuntime, string actor, string? key = null, bool lazy = true, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentRuntime);

        return agentRuntime.GetActorAsync(new ActorId(actor, key ?? "default"), lazy, cancellationToken);
    }

    /// <summary>
    /// Registers an actor factory with the runtime, associating it with a specific actor type.
    /// </summary>
    /// <typeparam name="TActor">The type of actor created by the factory.</typeparam>
    /// <param name="agentRuntime">The agent runtime.</param>
    /// <param name="type">The actor type to associate with the factory.</param>
    /// <param name="factoryFunc">A function that asynchronously creates the actor instance.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation, returning the registered actor type.</returns>
    public static ValueTask<ActorType> RegisterActorFactoryAsync<TActor>(
        this IAgentRuntime agentRuntime,
        ActorType type,
        Func<ActorId, IAgentRuntime, ValueTask<TActor>> factoryFunc,
        CancellationToken cancellationToken = default)
        where TActor : IRuntimeActor
    {
        Throw.IfNull(agentRuntime);
        Throw.IfNull(factoryFunc);

        return agentRuntime.RegisterActorFactoryAsync(
            type,
            async ValueTask<IRuntimeActor> (actorId, runtime) => await factoryFunc(actorId, runtime).ConfigureAwait(false),
            cancellationToken);
    }
}
