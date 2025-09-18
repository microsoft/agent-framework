// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.Metrics;
using System.Threading;
using System.Threading.Tasks;
using static Microsoft.Extensions.AI.Agents.Runtime.ActivityExtensions;
using Tel = Microsoft.Extensions.AI.Agents.Runtime.ActorRuntimeOpenTelemetryConsts;

namespace Microsoft.Extensions.AI.Agents.Runtime;

internal sealed class InProcessActorRuntime(
    IServiceProvider serviceProvider,
    IReadOnlyDictionary<ActorType, Func<IServiceProvider, IActorRuntimeContext, IActor>> actorFactories,
    IActorStateStorage storage)
{
    private static readonly ActivitySource ActivitySource = new(Tel.InProcessSourceName);
    private static readonly Meter Meter = new(Tel.InProcessSourceName);

    // Metrics following OpenTelemetry semantic conventions
    private static readonly Counter<long> ActorCreatedCounter = Meter.CreateCounter<long>(
        Tel.Client.ActorCount.Name,
        Tel.CountUnit,
        Tel.Client.ActorCount.Description);

    private static readonly Histogram<double> OperationDurationHistogram = Meter.CreateHistogram<double>(
        Tel.Client.OperationDuration.Name,
        "s",
        Tel.Client.OperationDuration.Description);

    private readonly object _createActorLock = new();
    private readonly IReadOnlyDictionary<ActorType, Func<IServiceProvider, IActorRuntimeContext, IActor>> _actorFactories = actorFactories;
    private readonly ConcurrentDictionary<ActorId, InProcessActorContext> _actors = [];

    public IActorStateStorage Storage { get; } = storage;
    public IServiceProvider Services { get; } = serviceProvider;

    internal InProcessActorContext GetOrCreateActor(ActorId actorId)
    {
        var stopwatch = Stopwatch.StartNew();

        // Create span following OpenTelemetry conventions for RPC operations
        using var activity = ActivitySource.StartActivity(
            Tel.SpanNames.FormatActorOperation(Tel.Operations.GetActor));

        try
        {
            if (this._actors.TryGetValue(actorId, out var context))
            {
                activity.SetupActorOperation(actorId, exists: true);
                activity.Event(ActorStarted, actorId);
                return context;
            }

            if (!this._actorFactories.TryGetValue(actorId.Type, out var factory))
            {
                var errorMessage = $"No factory registered for actor type '{actorId.Type}'";
                var exception = new InvalidOperationException(errorMessage);

                activity.SetupActorOperation(actorId, exists: false);
                activity.RecordFailure(exception, Tel.ErrorInfo.Types.ActorNotFound);
                throw exception;
            }

            if (!this._actors.TryGetValue(actorId, out var actorContext))
            {
#if NETSTANDARD
                InProcessActorContext ValueFactory(ActorId actorId)
                {
                    var self = this;

                    return CreateActorInstance(actorId, self, factory);
                }

                actorContext = this._actors.GetOrAdd(actorId, ValueFactory);
#else
                static InProcessActorContext ValueFactory(
                    ActorId actorId,
                    (InProcessActorRuntime, Func<IServiceProvider, IActorRuntimeContext, IActor>) state)
                {
                    var (self, factory) = state;
                    return CreateActorInstance(actorId, self, factory);
                }

                actorContext = this._actors.GetOrAdd(actorId, ValueFactory, (this, factory));
#endif
            }

            activity.SetupActorOperation(actorId, exists: false);
            activity.RecordSuccess();
            return actorContext;
        }
        catch (Exception ex)
        {
            activity.RecordFailure(ex);
            throw;
        }
        finally
        {
            // Record operation duration metric
            var duration = stopwatch.Elapsed.TotalSeconds;
            OperationDurationHistogram.Record(duration,
                new KeyValuePair<string, object?>(Tel.Actor.Operation, Tel.Operations.GetActor),
                new KeyValuePair<string, object?>(Tel.Actor.Type, actorId.Type.Name));
        }
    }

    private static InProcessActorContext CreateActorInstance(ActorId actorId, InProcessActorRuntime self, Func<IServiceProvider, IActorRuntimeContext, IActor> factory)
    {
        lock (self._createActorLock)
        {
            // Create nested span for actor creation
            var createActivity = ActivitySource.StartActivity(
                Tel.SpanNames.FormatActorOperation(Tel.Operations.CreateActor));
            InProcessActorContext? instance = null;
            try
            {
                createActivity.SetupActorOperation(actorId);

                instance = new InProcessActorContext(actorId, self, factory);
                instance.Start();

                createActivity.Complete(ActorCreated, actorId, [(Tel.Actor.Started, true)]);

                // Record metrics for successful actor creation
                ActorCreatedCounter.Add(1, new KeyValuePair<string, object?>(Tel.Actor.Type, actorId.Type.Name));
                return instance;
            }
            catch (Exception ex)
            {
                instance?.Dispose();
                createActivity.RecordFailure(ex);
                throw;
            }
        }
    }
}

internal sealed class InProcessActorClient(InProcessActorRuntime runtime) : IActorClient
{
    private static readonly ActivitySource ActivitySource = new(Tel.InProcessSourceName);
    private static readonly Meter ClientMeter = new(Tel.InProcessSourceName);
    private static readonly Counter<long> RequestCounter = ClientMeter.CreateCounter<long>(
        Tel.Client.RequestCount.Name,
        Tel.CountUnit,
        Tel.Client.RequestCount.Description);
    private static readonly Histogram<double> ClientOperationDurationHistogram = ClientMeter.CreateHistogram<double>(
        Tel.Client.OperationDuration.Name,
        "s",
        Tel.Client.OperationDuration.Description);

    private readonly InProcessActorRuntime _runtime = runtime;

    public ValueTask<ActorResponseHandle> GetResponseAsync(ActorId actorId, string messageId, CancellationToken cancellationToken)
    {
        // Create span for get response operation
        using var activity = ActivitySource.StartActivity(
            Tel.SpanNames.FormatRequestOperation(Tel.Operations.ReceiveResponse));

        activity.SetupRequestOperation(actorId, messageId, service: "ActorClient", rpcMethod: "GetResponse");

        var actorContext = this._runtime.GetOrCreateActor(actorId);
        if (actorContext.TryGetResponseHandle(messageId, out var handle))
        {
            return new(handle);
        }

        return new(new NotFoundActorResponseHandle(actorId, messageId));
    }

    public ValueTask<ActorResponseHandle> SendRequestAsync(ActorRequest request, CancellationToken cancellationToken)
    {
        var stopwatch = Stopwatch.StartNew();

        // Create span for send request operation following RPC client conventions
        using var activity = ActivitySource.StartActivity(
            Tel.SpanNames.FormatRequestOperation(Tel.Operations.SendRequest));

        try
        {
            activity.SetupRequestOperation(request.ActorId, request.MessageId, request.Method);

            // Ensure the message is enqueued on the actor's inbox, getting a response handle for it.
            var actorId = request.ActorId;
            var actorContext = this._runtime.GetOrCreateActor(actorId);
            var response = actorContext.SendRequest(request);

            activity.Complete(MessageSent, actorId, Sent, (Tel.Message.Id, request.MessageId));

            // Record request metric
            RequestCounter.Add(1,
                new KeyValuePair<string, object?>(Tel.Actor.Type, actorId.Type.Name),
                new KeyValuePair<string, object?>(Tel.Message.Method, request.Method));

            return new(response);
        }
        catch (Exception ex)
        {
            activity.RecordFailure(ex, null, (Tel.Request.Status, "failed"));
            throw;
        }
        finally
        {
            // Record operation duration
            var duration = stopwatch.Elapsed.TotalSeconds;
            ClientOperationDurationHistogram.Record(duration,
                new KeyValuePair<string, object?>(Tel.Actor.Operation, Tel.Operations.SendRequest),
                new KeyValuePair<string, object?>(Tel.Actor.Type, request.ActorId.Type.Name));
        }
    }
}
