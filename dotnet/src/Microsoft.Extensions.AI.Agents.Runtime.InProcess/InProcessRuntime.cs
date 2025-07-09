// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess;

/// <summary>
/// Provides an in-process/in-memory implementation of the agent runtime.
/// </summary>
public sealed partial class InProcessRuntime : IAgentRuntime, IAsyncDisposable
{
    private readonly Dictionary<ActorType, Func<ActorId, IAgentRuntime, ValueTask<IRuntimeActor>>> _actorFactories = [];
    private readonly Dictionary<string, ISubscriptionDefinition> _subscriptions = [];
    private readonly ConcurrentQueue<MessageDelivery> _messageDeliveryQueue = new();

    private CancellationTokenSource? _shutdownSource;
    private CancellationTokenSource? _finishSource;
    private Task _messageDeliveryTask = Task.CompletedTask;
    private Func<bool> _shouldContinue = () => true;

    // Exposed for testing purposes.
    internal int _messageQueueCount;
    internal readonly Dictionary<ActorId, IRuntimeActor> _actorInstances = [];

    /// <summary>
    /// Gets or sets a value indicating whether actors should receive messages they send themselves.
    /// </summary>
    public bool DeliverToSelf { get; set; }

    /// <inheritdoc/>
    public async ValueTask DisposeAsync()
    {
        await this.RunUntilIdleAsync().ConfigureAwait(false);
        this._shutdownSource?.Dispose();
        this._finishSource?.Dispose();
    }

    /// <summary>
    /// Starts the runtime service.
    /// </summary>
    /// <param name="cancellationToken">Token to monitor for shutdown requests.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    /// <exception cref="InvalidOperationException">Thrown if the runtime is already started.</exception>
    public Task StartAsync(CancellationToken cancellationToken = default)
    {
        if (this._shutdownSource != null)
        {
            throw new InvalidOperationException("Runtime is already running.");
        }

        this._shutdownSource = new CancellationTokenSource();
        this._messageDeliveryTask = Task.Run(() => this.RunAsync(this._shutdownSource.Token), cancellationToken);

        return Task.CompletedTask;
    }

    /// <summary>
    /// Stops the runtime service.
    /// </summary>
    /// <param name="cancellationToken">Token to propagate when stopping the runtime.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    /// <exception cref="InvalidOperationException">Thrown if the runtime is in the process of stopping.</exception>
    public Task StopAsync(CancellationToken cancellationToken = default)
    {
        if (this._shutdownSource != null)
        {
            if (this._finishSource != null)
            {
                throw new InvalidOperationException("Runtime is already stopping.");
            }

            this._finishSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);

            this._shutdownSource.Cancel();
        }

        return Task.CompletedTask;
    }

    /// <summary>
    /// This will run until the message queue is empty and then stop the runtime.
    /// </summary>
    public async Task RunUntilIdleAsync(CancellationToken cancellationToken = default)
    {
        Func<bool> oldShouldContinue = this._shouldContinue;
        this._shouldContinue = () => !this._messageDeliveryQueue.IsEmpty;

        // TODO: Do we want detach semantics?
        await this._messageDeliveryTask.ConfigureAwait(false);

        this._shouldContinue = oldShouldContinue;
    }

    /// <inheritdoc/>
    public ValueTask PublishMessageAsync(object message, TopicId topic, ActorId? sender = null, string? messageId = null, CancellationToken cancellationToken = default)
    {
        return this.ExecuteTracedAsync(async () =>
        {
            MessageDelivery delivery =
                new MessageEnvelope(message, messageId, cancellationToken)
                    .WithSender(sender)
                    .ForPublish(topic, this.PublishMessageServicerAsync);

            this._messageDeliveryQueue.Enqueue(delivery);
            Interlocked.Increment(ref this._messageQueueCount);

            await delivery.ResultTask.ConfigureAwait(false);
        });
    }

    /// <inheritdoc/>
    public async ValueTask<object?> SendMessageAsync(object message, ActorId recipient, ActorId? sender = null, string? messageId = null, CancellationToken cancellationToken = default)
    {
        return await this.ExecuteTracedAsync(async () =>
        {
            MessageDelivery delivery =
                new MessageEnvelope(message, messageId, cancellationToken)
                    .WithSender(sender)
                    .ForSend(recipient, this.SendMessageServicerAsync);

            this._messageDeliveryQueue.Enqueue(delivery);
            Interlocked.Increment(ref this._messageQueueCount);

            return await delivery.ResultTask.ConfigureAwait(false);
        }).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public async ValueTask<ActorId> GetActorAsync(ActorId actorId, bool lazy = true, CancellationToken cancellationToken = default)
    {
        if (!lazy)
        {
            await this.EnsureActorAsync(actorId, cancellationToken).ConfigureAwait(false);
        }

        return actorId;
    }

    /// <inheritdoc/>
    public ValueTask<ActorId> GetActorAsync(ActorType actorType, string? key = null, bool lazy = true, CancellationToken cancellationToken = default)
        => this.GetActorAsync(actorType.Name, key, lazy, cancellationToken);

    /// <inheritdoc/>
    public ValueTask<ActorId> GetActorAsync(string actor, string? key = null, bool lazy = true, CancellationToken cancellationToken = default)
        => this.GetActorAsync(new ActorId(actor, key ?? "default"), lazy, cancellationToken);

    /// <inheritdoc/>
    public async ValueTask<ActorMetadata> GetActorMetadataAsync(ActorId actorId, CancellationToken cancellationToken = default)
    {
        IRuntimeActor actor = await this.EnsureActorAsync(actorId, cancellationToken).ConfigureAwait(false);
        return actor.Metadata;
    }

    /// <inheritdoc/>
    public async ValueTask<TActor> TryGetUnderlyingActorInstanceAsync<TActor>(ActorId actorId, CancellationToken cancellationToken = default) where TActor : IRuntimeActor
    {
        IRuntimeActor actor = await this.EnsureActorAsync(actorId, cancellationToken).ConfigureAwait(false);

        if (actor is not TActor concreteActor)
        {
            throw new InvalidOperationException($"Actor with name {actorId.Type} is not of type {typeof(TActor).Name}.");
        }

        return concreteActor;
    }

    /// <inheritdoc/>
    public async ValueTask LoadActorStateAsync(ActorId actorId, JsonElement state, CancellationToken cancellationToken = default)
    {
        IRuntimeActor actor = await this.EnsureActorAsync(actorId, cancellationToken).ConfigureAwait(false);
        await actor.LoadStateAsync(state, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public async ValueTask<JsonElement> SaveActorStateAsync(ActorId actorId, CancellationToken cancellationToken = default)
    {
        IRuntimeActor actor = await this.EnsureActorAsync(actorId, cancellationToken).ConfigureAwait(false);
        return await actor.SaveStateAsync(cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public ValueTask AddSubscriptionAsync(ISubscriptionDefinition subscription, CancellationToken cancellationToken = default)
    {
        if (this._subscriptions.ContainsKey(subscription.Id))
        {
            throw new InvalidOperationException($"Subscription with id {subscription.Id} already exists.");
        }

        this._subscriptions.Add(subscription.Id, subscription);

        return default;
    }

    /// <inheritdoc/>
    public ValueTask RemoveSubscriptionAsync(string subscriptionId, CancellationToken cancellationToken = default)
    {
        if (!this._subscriptions.ContainsKey(subscriptionId))
        {
            throw new InvalidOperationException($"Subscription with id {subscriptionId} does not exist.");
        }

        this._subscriptions.Remove(subscriptionId);

        return default;
    }

    /// <inheritdoc/>
    public async ValueTask LoadStateAsync(JsonElement state, CancellationToken cancellationToken = default)
    {
        foreach (JsonProperty actorIdStr in state.EnumerateObject())
        {
            ActorId actorId = ActorId.Parse(actorIdStr.Name);

            if (this._actorFactories.ContainsKey(actorId.Type))
            {
                IRuntimeActor actor = await this.EnsureActorAsync(actorId, cancellationToken).ConfigureAwait(false);
                await actor.LoadStateAsync(actorIdStr.Value, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    /// <inheritdoc/>
    public async ValueTask<JsonElement> SaveStateAsync(CancellationToken cancellationToken = default)
    {
        Dictionary<string, JsonElement> state = [];
        foreach (ActorId actorId in this._actorInstances.Keys)
        {
            JsonElement actorState = await this._actorInstances[actorId].SaveStateAsync(cancellationToken).ConfigureAwait(false);
            state[actorId.ToString()] = actorState;
        }
        return JsonSerializer.SerializeToElement(state, InProcessRuntimeContext.Default.DictionaryStringJsonElement);
    }

    /// <summary>
    /// Registers an actor factory with the runtime, associating it with a specific actor type.
    /// </summary>
    /// <typeparam name="TActor">The type of actor created by the factory.</typeparam>
    /// <param name="type">The actor type to associate with the factory.</param>
    /// <param name="factoryFunc">A function that asynchronously creates the actor instance.</param>
    /// <param name="cancellationToken">A token to cancel the operation if needed.</param>
    /// <returns>A task representing the asynchronous operation, returning the registered actor type.</returns>
    public ValueTask<ActorType> RegisterActorFactoryAsync<TActor>(ActorType type, Func<ActorId, IAgentRuntime, ValueTask<TActor>> factoryFunc, CancellationToken cancellationToken = default) where TActor : IRuntimeActor
        // Declare the lambda return type explicitly, as otherwise the compiler will infer 'ValueTask<TActor>'
        // and recurse into the same call, causing a stack overflow.
        => this.RegisterActorFactoryAsync(type, async ValueTask<IRuntimeActor> (actorId, runtime) => await factoryFunc(actorId, runtime).ConfigureAwait(false), cancellationToken);

    /// <inheritdoc/>
    public async ValueTask<ActorType> RegisterActorFactoryAsync(ActorType type, Func<ActorId, IAgentRuntime, ValueTask<IRuntimeActor>> factoryFunc, CancellationToken cancellationToken = default)
    {
        if (this._actorFactories.ContainsKey(type))
        {
            throw new InvalidOperationException($"Actor with type {type} already exists.");
        }

        this._actorFactories.Add(type, factoryFunc);

        return type;
    }

    /// <inheritdoc/>
    public async ValueTask<IdProxyActor?> TryGetActorProxyAsync(ActorId actorId, CancellationToken cancellationToken = default)
    {
        IdProxyActor proxy = new(this, actorId);

        return proxy;
    }

    private async ValueTask ProcessNextMessageAsync(CancellationToken cancellation = default)
    {
        if (this._messageDeliveryQueue.TryDequeue(out MessageDelivery? delivery))
        {
            Interlocked.Decrement(ref this._messageQueueCount);
            Debug.WriteLine($"Processing message {delivery.Message.MessageId}...");
            await delivery.InvokeAsync(cancellation).ConfigureAwait(false);
        }
    }

    private async Task RunAsync(CancellationToken cancellation)
    {
        ConcurrentDictionary<Guid, Task> pendingTasks = [];
        while (!cancellation.IsCancellationRequested && this._shouldContinue())
        {
            // Get a unique task id.
            Guid taskId = Guid.NewGuid();

            // There is potentially a race condition here, but even if we leak a Task, we will
            // still catch it on the Finish() pass.
            ValueTask processTask = this.ProcessNextMessageAsync(cancellation);
            await Task.Yield();

            if (!processTask.IsCompleted)
            {
                pendingTasks.TryAdd(taskId, processTask.AsTask().ContinueWith(t => pendingTasks.TryRemove(taskId, out _), TaskScheduler.Current));
            }
        }

        // The pending task dictionary may contain null values when a race condition is experienced during
        // the prior "ContinueWith" call.  This could be solved with a ConcurrentDictionary, but locking
        // is entirely undesirable in this context.
        await Task.WhenAll(pendingTasks.Values.Where(task => task is not null)).ConfigureAwait(false);
        await this.FinishAsync(this._finishSource?.Token ?? CancellationToken.None).ConfigureAwait(false);
    }

    private async ValueTask PublishMessageServicerAsync(MessageEnvelope envelope, CancellationToken deliveryToken)
    {
        if (!envelope.Topic.HasValue)
        {
            throw new InvalidOperationException("Message must have a topic to be published.");
        }

        List<Exception>? exceptions = null;
        TopicId topic = envelope.Topic.Value;
        foreach (ISubscriptionDefinition subscription in this._subscriptions.Values.Where(subscription => subscription.Matches(topic)))
        {
            try
            {
                deliveryToken.ThrowIfCancellationRequested();

                ActorId? sender = envelope.Sender;

                using CancellationTokenSource combinedSource = CancellationTokenSource.CreateLinkedTokenSource(envelope.Cancellation, deliveryToken);

                ActorId actorId = subscription.MapToActor(topic);
                if (!this.DeliverToSelf && sender.HasValue && sender == actorId)
                {
                    continue;
                }

                MessageContext messageContext = new()
                {
                    MessageId = envelope.MessageId,
                    Sender = sender,
                    Topic = topic,
                    IsRpc = false
                };

                IRuntimeActor actor = await this.EnsureActorAsync(actorId, combinedSource.Token).ConfigureAwait(false);

                await actor.OnMessageAsync(envelope.Message, messageContext, combinedSource.Token).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                (exceptions ??= []).Add(ex);
            }
        }

        if (exceptions is not null)
        {
            throw new AggregateException("One or more exceptions occurred while processing the message.", exceptions);
        }
    }

    private async ValueTask<object?> SendMessageServicerAsync(MessageEnvelope envelope, CancellationToken deliveryToken)
    {
        if (!envelope.Receiver.HasValue)
        {
            throw new InvalidOperationException("Message must have a receiver to be sent.");
        }

        using CancellationTokenSource combinedSource = CancellationTokenSource.CreateLinkedTokenSource(envelope.Cancellation, deliveryToken);
        MessageContext messageContext = new()
        {
            MessageId = envelope.MessageId,
            Sender = envelope.Sender,
            IsRpc = false
        };

        ActorId receiver = envelope.Receiver.Value;
        IRuntimeActor actor = await this.EnsureActorAsync(receiver, combinedSource.Token).ConfigureAwait(false);

        return await actor.OnMessageAsync(envelope.Message, messageContext, combinedSource.Token).ConfigureAwait(false);
    }

    private async ValueTask<IRuntimeActor> EnsureActorAsync(ActorId actorId, CancellationToken cancellationToken)
    {
        if (!this._actorInstances.TryGetValue(actorId, out IRuntimeActor? actor))
        {
            if (!this._actorFactories.TryGetValue(actorId.Type, out Func<ActorId, IAgentRuntime, ValueTask<IRuntimeActor>>? factoryFunc))
            {
                throw new InvalidOperationException($"Actor with name {actorId.Type} not found.");
            }

            actor = await factoryFunc(actorId, this).ConfigureAwait(false);
            this._actorInstances.Add(actorId, actor);
        }

        return actor;
    }

    private async Task FinishAsync(CancellationToken token)
    {
        foreach (IRuntimeActor actor in this._actorInstances.Values)
        {
            if (!token.IsCancellationRequested && actor is IAsyncDisposable closeableActor)
            {
                await closeableActor.DisposeAsync().ConfigureAwait(false);
            }
        }

        if (this._shutdownSource is { } shutdownSource)
        {
            this._shutdownSource = null;
            shutdownSource.Dispose();
        }

        if (this._finishSource is { } finishSource)
        {
            this._finishSource = null;
            finishSource.Dispose();
        }
    }

#pragma warning disable CA1822 // Mark members as static
    private ValueTask<T> ExecuteTracedAsync<T>(Func<ValueTask<T>> func)
    {
        // TODO: Bind tracing
        return func();
    }

    private ValueTask ExecuteTracedAsync(Func<ValueTask> func)
    {
        // TODO: Bind tracing
        return func();
    }
#pragma warning restore CA1822 // Mark members as static

    [JsonSerializable(typeof(Dictionary<string, JsonElement>))]
    private sealed partial class InProcessRuntimeContext : JsonSerializerContext;
}
