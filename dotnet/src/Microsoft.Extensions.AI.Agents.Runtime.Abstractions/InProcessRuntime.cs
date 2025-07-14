// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

#pragma warning disable CA1711 // Identifiers should not have incorrect suffix

namespace Microsoft.Extensions.AI.Agents.Runtime.InProcess;

/// <summary>Provides an in-process/in-memory implementation of the agent runtime.</summary>
public sealed partial class InProcessRuntime : IAgentRuntime, IAsyncDisposable
{
    private static readonly UnboundedChannelOptions s_singleReaderOptions = new();

    private readonly Dictionary<ActorType, Func<ActorId, IAgentRuntime, ValueTask<IRuntimeActor>>> _actorFactories = [];
    private readonly Dictionary<string, ISubscriptionDefinition> _subscriptions = [];
    private readonly Channel<MessageToProcess> _messages = Channel.CreateUnbounded<MessageToProcess>(s_singleReaderOptions);
    private readonly CancellationTokenSource _shutdownTokenSource = new();

    private Task? _messageDeliveryTask;
    private int _remainingWork = 1; // initial count of 1 represents overall operation, decremented when shutting down.
    private int _signaledCompletion = 0;

    // Internal for testing purposes.
    internal readonly Dictionary<ActorId, IRuntimeActor> _actorInstances = [];

    /// <summary>Initializes a new instance of the in-memory runtime.</summary>
    public InProcessRuntime() { }

    /// <summary>Gets the number of pending work items.</summary>
    /// <remarks>Internal for testing purposes.</remarks>
    internal int MessageCountForTesting => this._remainingWork - (1 - this._signaledCompletion);

    /// <summary>Creates and starts a new <see cref="InProcessRuntime"/> instance.</summary>
    /// <returns>The started runtime.</returns>
    public static InProcessRuntime StartNew()
    {
        InProcessRuntime runtime = new();
        runtime.Start();
        return runtime;
    }

    /// <summary>Starts the runtime.</summary>
    /// <exception cref="InvalidOperationException">Thrown if the runtime is already started.</exception>
    public void Start()
    {
        ThrowIfInvalid(this._signaledCompletion != 0 || this._messageDeliveryTask is not null, "Runtime was already started or shutdown.");

        CancellationToken ct = this._shutdownTokenSource.Token;
        this._messageDeliveryTask = Task.Run(() => this.RunAsync(ct));
    }

    /// <inheritdoc/>
    public async ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref this._signaledCompletion, 1) == 0 && this._messageDeliveryTask is not null)
        {
            this.DecrementRemainingWork();
            this._shutdownTokenSource.Cancel();
            this._shutdownTokenSource.Dispose();
            await this._messageDeliveryTask.ConfigureAwait(false);
        }
    }

    /// <inheritdoc/>
    public ValueTask PublishMessageAsync(object message, TopicId topic, ActorId? sender = null, string? messageId = null, CancellationToken cancellationToken = default)
    {
        MessageToProcess m = new(this, message, messageId, sender, topic, cancellationToken);

        this.IncrementRemainingWork();
        this._messages.Writer.TryWrite(m);

        return new(m.ResultTcs.Task);
    }

    /// <inheritdoc/>
    public ValueTask<object?> SendMessageAsync(object message, ActorId recipient, ActorId? sender = null, string? messageId = null, CancellationToken cancellationToken = default)
    {
        MessageToProcess m = new(this, message, messageId, sender, recipient, cancellationToken);

        this.IncrementRemainingWork();
        this._messages.Writer.TryWrite(m);

        return new(m.ResultTcs.Task);
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
        ThrowIfInvalid(this._subscriptions.ContainsKey(subscription.Id), "Subscription with the specified ID already exists.");

        this._subscriptions.Add(subscription.Id, subscription);

        return default;
    }

    /// <inheritdoc/>
    public ValueTask RemoveSubscriptionAsync(string subscriptionId, CancellationToken cancellationToken = default)
    {
        ThrowIfInvalid(!this._subscriptions.ContainsKey(subscriptionId), "Subscription with the specified ID does not exist.");

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
        foreach (KeyValuePair<ActorId, IRuntimeActor> actor in this._actorInstances)
        {
            state[actor.Key.ToString()] = await actor.Value.SaveStateAsync(cancellationToken).ConfigureAwait(false);
        }

        return JsonSerializer.SerializeToElement(state, InProcessRuntimeContext.Default.DictionaryStringJsonElement);
    }

    /// <inheritdoc/>
    public async ValueTask<ActorType> RegisterActorFactoryAsync(ActorType type, Func<ActorId, IAgentRuntime, ValueTask<IRuntimeActor>> factoryFunc, CancellationToken cancellationToken = default)
    {
        ThrowIfInvalid(this._actorFactories.ContainsKey(type), "Actor type already registered.");

        this._actorFactories.Add(type, factoryFunc);

        return type;
    }

    /// <inheritdoc/>
    public async ValueTask<IdProxyActor?> TryGetActorProxyAsync(ActorId actorId, CancellationToken cancellationToken = default) =>
        new(this, actorId);

    private async Task RunAsync(CancellationToken cancellationToken)
    {
        try
        {
            Dictionary<long, Task> pendingTasks = [];

            long currentId = 0;
            await foreach (MessageToProcess message in this._messages.Reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
            {
                this.DecrementRemainingWork();

                ValueTask processTask = message.InvokeAsync(cancellationToken);
                if (!processTask.IsCompleted)
                {
                    currentId++;
                    Task t = WaitAndRemoveAsync(currentId, processTask);
                    lock (pendingTasks)
                    {
                        if (!t.IsCompleted)
                        {
                            pendingTasks.Add(currentId, t);
                        }
                    }

                    async Task WaitAndRemoveAsync(long taskId, ValueTask processTask)
                    {
                        try
                        {
                            await processTask.ConfigureAwait(false);
                        }
                        finally
                        {
                            lock (pendingTasks)
                            {
                                pendingTasks.Remove(taskId);
                            }
                        }
                    }
                }
            }

            await Task.WhenAll(pendingTasks.Values).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            // Ignore cancellation exceptions, as they are expected when the runtime is shutting down.
        }
        finally
        {
            foreach (var actor in this._actorInstances)
            {
                if (actor.Value is IAsyncDisposable closeableActor)
                {
                    await closeableActor.DisposeAsync().ConfigureAwait(false);
                }
            }
        }
    }

    private static readonly Func<MessageToProcess, CancellationToken, ValueTask<object?>> s_publishServicer =
        async (MessageToProcess message, CancellationToken cancellationToken) =>
        {
            Debug.Assert(message.Topic.HasValue);

            List<Task>? tasks = null;
            TopicId topic = message.Topic!.Value;
            foreach (KeyValuePair<string, ISubscriptionDefinition> subscription in message.Runtime._subscriptions)
            {
                if (subscription.Value.Matches(topic))
                {
                    (tasks ??= []).Add(ProcessSubscriptionAsync(message, subscription.Value, topic, cancellationToken));
                }

                static async Task ProcessSubscriptionAsync(
                    MessageToProcess message, ISubscriptionDefinition subscription, TopicId topic, CancellationToken cancellationToken)
                {
                    using CancellationTokenSource combinedSource = CancellationTokenSource.CreateLinkedTokenSource(message.Cancellation, cancellationToken);
                    combinedSource.Token.ThrowIfCancellationRequested();

                    ActorId actorId = subscription.MapToActor(topic);
                    ActorId? sender = message.Sender;
                    if (sender is null || sender != actorId)
                    {
                        IRuntimeActor actor = await message.Runtime.EnsureActorAsync(actorId, combinedSource.Token).ConfigureAwait(false);
                        await actor.OnMessageAsync(message.Message, new()
                        {
                            MessageId = message.MessageId,
                            Sender = sender,
                            Topic = topic,
                        }, combinedSource.Token).ConfigureAwait(false);
                    }
                }
            }

            if (tasks is not null)
            {
                await Task.WhenAll(tasks).ConfigureAwait(false);
            }

            // This method is effectively void, with the result never being used. But it's typed the same as SendMessageServicerAsync
            // in order to be able to share the same consuming code.
            return null;
        };

    private static readonly Func<MessageToProcess, CancellationToken, ValueTask<object?>> s_sendServicer =
        async (MessageToProcess message, CancellationToken cancellationToken) =>
        {
            Debug.Assert(message.Receiver.HasValue);

            using CancellationTokenSource combinedSource = CancellationTokenSource.CreateLinkedTokenSource(message.Cancellation, cancellationToken);

            IRuntimeActor actor = await message.Runtime.EnsureActorAsync(message.Receiver!.Value, combinedSource.Token).ConfigureAwait(false);
            return await actor.OnMessageAsync(message.Message, new()
            {
                MessageId = message.MessageId,
                Sender = message.Sender,
            }, combinedSource.Token).ConfigureAwait(false);
        };

    private async ValueTask<IRuntimeActor> EnsureActorAsync(ActorId actorId, CancellationToken cancellationToken)
    {
        if (!this._actorInstances.TryGetValue(actorId, out IRuntimeActor? actor))
        {
            this._actorFactories.TryGetValue(actorId.Type, out Func<ActorId, IAgentRuntime, ValueTask<IRuntimeActor>>? factoryFunc);
            ThrowIfInvalid(factoryFunc is null, "Actor with the specified name not found.");

            actor = await factoryFunc(actorId, this).ConfigureAwait(false);
            this._actorInstances.Add(actorId, actor);
        }

        return actor;
    }

    private void IncrementRemainingWork()
    {
        int current;
        do
        {
            current = this._remainingWork;
            ThrowIfInvalid(current <= 0, "Runtime has already shut down.");
        }
        while (Interlocked.CompareExchange(ref this._remainingWork, current + 1, current) != current);
    }

    private void DecrementRemainingWork()
    {
        int current;
        do
        {
            current = this._remainingWork;
            ThrowIfInvalid(current <= 0, "Runtime has already shut down.");
        }
        while (Interlocked.CompareExchange(ref this._remainingWork, current - 1, current) != current);

        if (current == 1)
        {
            this._messages.Writer.TryComplete();
        }
    }

    private static void ThrowIfInvalid([DoesNotReturnIf(true)] bool isInvalid, string message)
    {
        if (isInvalid)
        {
            throw new InvalidOperationException(message);
        }
    }

    [JsonSerializable(typeof(Dictionary<string, JsonElement>))]
    private sealed partial class InProcessRuntimeContext : JsonSerializerContext;

    private sealed class MessageToProcess
    {
        public MessageToProcess(InProcessRuntime runtime, object message, string? messageId, ActorId? sender, ActorId receiver, CancellationToken cancellationToken) :
            this(runtime, message, messageId, sender, s_sendServicer, cancellationToken)
        {
            this.Receiver = Throw.IfNull(receiver);
        }

        public MessageToProcess(InProcessRuntime runtime, object message, string? messageId, ActorId? sender, TopicId topic, CancellationToken cancellationToken) :
            this(runtime, message, messageId, sender, s_publishServicer, cancellationToken)
        {
            this.Topic = Throw.IfNull(topic);
        }

        private MessageToProcess(InProcessRuntime runtime, object message, string? messageId, ActorId? sender, Func<MessageToProcess, CancellationToken, ValueTask<object?>> servicer, CancellationToken cancellationToken)
        {
            this.Runtime = runtime;
            this.Message = message;
            this.MessageId = messageId ?? Guid.NewGuid().ToString();
            this.Sender = sender;
            this.Servicer = servicer;
            this.Cancellation = cancellationToken;
        }

        public InProcessRuntime Runtime { get; }
        public object Message { get; }
        public string MessageId { get; }
        public ActorId? Sender { get; }
        public TopicId? Topic { get; }
        public ActorId? Receiver { get; }
        public CancellationToken Cancellation { get; }
        public TaskCompletionSource<object?> ResultTcs { get; } = new();
        private Func<MessageToProcess, CancellationToken, ValueTask<object?>> Servicer { get; }

        public async ValueTask InvokeAsync(CancellationToken cancellationToken)
        {
            try
            {
                this.ResultTcs.SetResult(await this.Servicer(this, cancellationToken).ConfigureAwait(false));
            }
            catch (OperationCanceledException exception)
            {
                this.ResultTcs.TrySetCanceled(exception.CancellationToken);
            }
            catch (Exception exception)
            {
                this.ResultTcs.SetException(exception);
            }
        }
    }
}
