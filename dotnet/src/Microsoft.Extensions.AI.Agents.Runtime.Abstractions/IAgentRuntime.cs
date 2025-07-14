// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Defines the runtime environment for actors, managing message sending, subscriptions, actor resolution, and state persistence,
/// all in support of agent-based architectures.
/// </summary>
public interface IAgentRuntime : ISaveState
{
    /// <summary>
    /// Sends a message to an actor and gets a response.
    /// This method should be used to communicate directly with an actor.
    /// </summary>
    /// <param name="message">The message to send.</param>
    /// <param name="recipient">The actor to send the message to.</param>
    /// <param name="sender">The actor sending the message. Should be <c>null</c> if sent from an external source.</param>
    /// <param name="messageId">A unique identifier for the message. If <c>null</c>, a new ID will be generated.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation, returning the response from the actor.</returns>
    ValueTask<object?> SendMessageAsync(object message, ActorId recipient, ActorId? sender = null, string? messageId = null, CancellationToken cancellationToken = default);

    /// <summary>
    /// Publishes a message to all agents subscribed to the given topic.
    /// No responses are expected from publishing.
    /// </summary>
    /// <param name="message">The message to publish.</param>
    /// <param name="topic">The topic to publish the message to.</param>
    /// <param name="sender">The actor sending the message. Defaults to <c>null</c>.</param>
    /// <param name="messageId">A unique message ID. If <c>null</c>, a new one will be generated.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    ValueTask PublishMessageAsync(object message, TopicId topic, ActorId? sender = null, string? messageId = null, CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves an actor by its unique identifier.
    /// </summary>
    /// <param name="actorId">The unique identifier of the actor.</param>
    /// <param name="lazy">If <c>true</c>, the actor is fetched lazily.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation, returning the actor's ID.</returns>
    ValueTask<ActorId> GetActorAsync(ActorId actorId, bool lazy = true, CancellationToken cancellationToken = default);

    /// <summary>
    /// Saves the state of an actor.
    /// The result must be JSON serializable.
    /// </summary>
    /// <param name="actorId">The ID of the actor whose state is being saved.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation, returning a dictionary of the saved state.</returns>
    ValueTask<JsonElement> SaveActorStateAsync(ActorId actorId, CancellationToken cancellationToken = default);

    /// <summary>
    /// Loads the saved state into an actor.
    /// </summary>
    /// <param name="actorId">The ID of the actor whose state is being restored.</param>
    /// <param name="state">The state dictionary to restore.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    ValueTask LoadActorStateAsync(ActorId actorId, JsonElement state, CancellationToken cancellationToken = default);

    /// <summary>
    /// Retrieves metadata for an actor.
    /// </summary>
    /// <param name="actorId">The ID of the actor.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation, returning the actor's metadata.</returns>
    ValueTask<ActorMetadata> GetActorMetadataAsync(ActorId actorId, CancellationToken cancellationToken = default);

    /// <summary>
    /// Adds a new subscription for the runtime to handle when processing published messages.
    /// </summary>
    /// <param name="subscription">The subscription to add.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    ValueTask AddSubscriptionAsync(ISubscriptionDefinition subscription, CancellationToken cancellationToken = default);

    /// <summary>
    /// Removes a subscription from the runtime.
    /// </summary>
    /// <param name="subscriptionId">The unique identifier of the subscription to remove.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    /// <exception cref="KeyNotFoundException">Thrown if the subscription does not exist.</exception>
    ValueTask RemoveSubscriptionAsync(string subscriptionId, CancellationToken cancellationToken = default);

    /// <summary>
    /// Registers an actor factory with the runtime, associating it with a specific actor type.
    /// The type must be unique.
    /// </summary>
    /// <param name="type">The actor type to associate with the factory.</param>
    /// <param name="factoryFunc">A function that asynchronously creates the actor instance.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation, returning the registered <see cref="ActorType"/>.</returns>
    ValueTask<ActorType> RegisterActorFactoryAsync(ActorType type, Func<ActorId, IAgentRuntime, ValueTask<IRuntimeActor>> factoryFunc, CancellationToken cancellationToken = default);

    /// <summary>
    /// Attempts to retrieve an <see cref="IdProxyActor"/> for the specified actor.
    /// </summary>
    /// <param name="actorId">The ID of the actor.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation, returning an <see cref="IdProxyActor"/> if successful.</returns>
    ValueTask<IdProxyActor?> TryGetActorProxyAsync(ActorId actorId, CancellationToken cancellationToken = default);
}
