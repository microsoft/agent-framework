// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Provides a base implementation of <see cref="IRuntimeActor"/>.
/// </summary>
public abstract class RuntimeActor : IRuntimeActor
{
    private static readonly JsonElement s_emptyElement = JsonDocument.Parse("{}").RootElement;

    /// <summary>
    /// The activity source for tracing.
    /// </summary>
    public static readonly ActivitySource TraceSource = new($"{typeof(IRuntimeActor).Namespace}");

    private readonly Dictionary<Type, HandlerInvoker> _handlerInvokers = [];
    private readonly IAgentRuntime _runtime;

    private delegate ValueTask<object?> HandlerInvoker(object? message, MessageContext messageContext, CancellationToken cancellationToken);

    /// <summary>
    /// Provides logging capabilities used for diagnostic and operational information.
    /// </summary>
    protected internal ILogger Logger { get; }

    /// <summary>
    /// Gets the unique identifier of the actor.
    /// </summary>
    public ActorId Id { get; }

    /// <summary>
    /// Gets the metadata of the actor.
    /// </summary>
    public ActorMetadata Metadata { get; }

    /// <summary>
    /// Initializes a new instance of the RuntimeActor class with the specified identifier, runtime, description, and optional logger.
    /// </summary>
    /// <param name="id">The unique identifier of the actor.</param>
    /// <param name="runtime">The runtime environment in which the actor operates.</param>
    /// <param name="description">A brief description of the actor's purpose.</param>
    /// <param name="logger">An optional logger for recording diagnostic information.</param>
    protected RuntimeActor(
        ActorId id,
        IAgentRuntime runtime,
        string description,
        ILogger? logger = null)
    {
        this.Id = id;
        this._runtime = runtime;
        this.Logger = logger ?? NullLogger.Instance;

        this.Metadata = new ActorMetadata(this.Id.Type, this.Id.Key, description);
    }

    /// <summary>Registers a handler for <typeparamref name="TInput"/>.</summary>
    /// <typeparam name="TInput">The type of the input message for the handler.</typeparam>
    /// <param name="messageHandler">The handler function that processes the message.</param>
    /// <exception cref="InvalidOperationException">Thrown when a handler for the specified type is already registered.</exception>
    /// <remarks>
    /// The base implementation of <see cref="OnMessageAsync"/> will use these registered handlers to process incoming messages.
    /// </remarks>
    protected void RegisterMessageHandler<TInput>(Func<TInput, MessageContext, CancellationToken, ValueTask> messageHandler)
    {
        if (messageHandler is null)
        {
            throw new ArgumentNullException(nameof(messageHandler));
        }

        if (this._handlerInvokers.ContainsKey(typeof(TInput)))
        {
            throw new InvalidOperationException($"A handler for type {typeof(TInput)} is already registered.");
        }

        this._handlerInvokers.Add(
            typeof(TInput),
            async (message, messageContext, cancellationToken) =>
            {
                await messageHandler((TInput)message!, messageContext, cancellationToken).ConfigureAwait(false);
                return null; // No return value for void handlers
            });
    }

    /// <summary>Registers a handler for <typeparamref name="TInput"/> that produces a <typeparamref name="TOutput"/>.</summary>
    /// <typeparam name="TInput">The type of the input message for the handler.</typeparam>
    /// <typeparam name="TOutput">The type of the output message for the handler.</typeparam>
    /// <param name="messageHandler">The handler function that processes the message.</param>
    /// <exception cref="InvalidOperationException">Thrown when a handler for the specified type is already registered.</exception>
    /// <remarks>
    /// The base implementation of <see cref="OnMessageAsync"/> will use these registered handlers to process incoming messages.
    /// </remarks>
    protected void RegisterMessageHandler<TInput, TOutput>(Func<TInput, MessageContext, CancellationToken, ValueTask<TOutput>> messageHandler)
    {
        if (messageHandler is null)
        {
            throw new ArgumentNullException(nameof(messageHandler));
        }

        if (this._handlerInvokers.ContainsKey(typeof(TInput)))
        {
            throw new InvalidOperationException($"A handler for type {typeof(TInput)} is already registered.");
        }

        this._handlerInvokers.Add(
            typeof(TInput),
            async (message, messageContext, cancellationToken) =>
            {
                TOutput? result = await messageHandler((TInput)message!, messageContext, cancellationToken).ConfigureAwait(false);
                return (object?)result;
            });
    }

    /// <summary>
    /// Handles an incoming message by determining its type and invoking the corresponding handler method if available.
    /// </summary>
    /// <param name="message">The message object to be handled.</param>
    /// <param name="messageContext">The context associated with the message.</param>
    /// <param name="cancellationToken">A token used to cancel the operation if needed.</param>
    /// <returns>A ValueTask that represents the asynchronous operation, containing the response object or null.</returns>
    public ValueTask<object?> OnMessageAsync(object message, MessageContext messageContext, CancellationToken cancellationToken = default)
    {
        // Get the handler for the message type, and invoke it, if it exists.
        if (message is not null && this._handlerInvokers.TryGetValue(message.GetType(), out HandlerInvoker? handlerInvoker))
        {
            return handlerInvoker(message, messageContext, cancellationToken);
        }

        return new((object?)null);
    }

    /// <inheritdoc/>
    public virtual ValueTask<JsonElement> SaveStateAsync(CancellationToken cancellationToken = default) =>
        new(s_emptyElement);

    /// <inheritdoc/>
    public virtual ValueTask LoadStateAsync(JsonElement state, CancellationToken cancellationToken = default) =>
        default;

    /// <summary>
    /// Sends a message to a specified recipient actor through the runtime.
    /// </summary>
    /// <param name="actor">The requested actor's type.</param>
    /// <param name="cancellationToken">A token used to cancel the operation if needed.</param>
    /// <returns>A ValueTask that represents the asynchronous operation, returning the response object or null.</returns>
    protected async ValueTask<ActorId?> GetActorAsync(ActorType actor, CancellationToken cancellationToken = default)
    {
        try
        {
            return await this._runtime.GetActorAsync(actor, lazy: false, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (InvalidOperationException)
        {
            return null;
        }
    }

    /// <summary>
    /// Sends a message to a specified recipient actor through the runtime.
    /// </summary>
    /// <param name="message">The message object to send.</param>
    /// <param name="recipient">The recipient actor's identifier.</param>
    /// <param name="messageId">An optional identifier for the message.</param>
    /// <param name="cancellationToken">A token used to cancel the operation if needed.</param>
    /// <returns>A ValueTask that represents the asynchronous operation, returning the response object or null.</returns>
    protected ValueTask<object?> SendMessageAsync(object message, ActorId recipient, string? messageId = null, CancellationToken cancellationToken = default) =>
        this._runtime.SendMessageAsync(message, recipient, sender: this.Id, messageId, cancellationToken);

    /// <summary>
    /// Publishes a message to all actors subscribed to a specific topic through the runtime.
    /// </summary>
    /// <param name="message">The message object to publish.</param>
    /// <param name="topic">The topic identifier to which the message is published.</param>
    /// <param name="messageId">An optional identifier for the message.</param>
    /// <param name="cancellationToken">A token used to cancel the operation if needed.</param>
    /// <returns>A ValueTask that represents the asynchronous publish operation.</returns>
    protected ValueTask PublishMessageAsync(object message, TopicId topic, string? messageId = null, CancellationToken cancellationToken = default) =>
        this._runtime.PublishMessageAsync(message, topic, sender: this.Id, messageId, cancellationToken);
}
