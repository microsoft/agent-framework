// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using static Microsoft.Extensions.AI.Agents.Runtime.ActivityExtensions;
using Tel = Microsoft.Extensions.AI.Agents.Runtime.ActorRuntimeOpenTelemetryConsts;

namespace Microsoft.Extensions.AI.Agents.Runtime;

internal sealed class InProcessActorContext : IActorRuntimeContext, IAsyncDisposable, IDisposable
{
    private static readonly ActivitySource ActivitySource = new(Tel.InProcessSourceName);

    private readonly CancellationTokenSource _cts = new();
    private readonly Channel<ActorMessage> _pendingMessages = Channel.CreateUnbounded<ActorMessage>();
    private readonly object _lock = new();
    private readonly Dictionary<string, ActorInboxEntry> _inbox = [];
    private readonly InProcessActorRuntime _runtime;
    private readonly IActor _actorInstance;
    private readonly ILogger<InProcessActorContext> _logger;
    private Task? _actorRunTask;

    public InProcessActorContext(
        ActorId ActorId,
        InProcessActorRuntime runtime,
        Func<IServiceProvider, IActorRuntimeContext, IActor> actorFactory)
    {
        this._runtime = runtime;
        this.ActorId = ActorId;
        this._logger = runtime.Services.GetRequiredService<ILogger<InProcessActorContext>>();
        this._actorInstance = actorFactory(runtime.Services, this);

        Log.ActorContextCreated(this._logger, this.ActorId.ToString());
    }

    public ActorId ActorId { get; }

    private IActorStateStorage Storage => this._runtime.Storage;

    public void Start()
    {
        using var activity = ActivitySource.StartActivity(
            Tel.SpanNames.FormatActorOperation(Tel.Operations.StartActor));

        activity.SetActorAttributes(this.ActorId, "start");

        try
        {
            Log.ActorContextStarting(this._logger, this.ActorId.ToString());
            this._actorRunTask = this._actorInstance.RunAsync(this._cts.Token).AsTask();
            Log.ActorContextStarted(this._logger, this.ActorId.ToString());

            activity.Complete(ActorStarted, this.ActorId, [(Tel.Actor.Started, true)]);
        }
        catch (Exception ex)
        {
            activity.Fail(ex);
            throw;
        }
    }

    public void EnqueueMessage(ActorMessage message)
    {
        using var activity = ActivitySource.StartActivity(
            Tel.SpanNames.FormatMessageOperation(Tel.Operations.ReceiveMessage));

        var messageId = message switch
        {
            ActorRequestMessage requestMessage => requestMessage.MessageId,
            ActorResponseMessage responseMessage => responseMessage.MessageId,
            _ => "unknown"
        };

        // Set message tracing attributes
        activity.SetActorAttributes(this.ActorId);
        activity.SetMessageAttributes(messageId, message.Type.ToString());

        try
        {
            Log.MessageEnqueued(this._logger, this.ActorId.ToString(), messageId, message.Type.ToString());
            this._pendingMessages.Writer.TryWrite(message);

            activity.Complete(MessageReceived, this.ActorId, Enqueued,
                (Tel.Message.Id, messageId), (Tel.Message.Type, message.Type.ToString()));
        }
        catch (Exception ex)
        {
            activity.RecordFailure(ex, null, (Tel.Message.Status, "failed"));
            throw;
        }
    }

    public bool TryGetResponseHandle(string messageId, [NotNullWhen(true)] out ActorResponseHandle? handle)
    {
        lock (this._lock)
        {
            if (!this._inbox.TryGetValue(messageId, out var entry))
            {
                handle = null;
                return false;
            }

            handle = new InProcessActorResponseHandle(this, entry);
            return true;
        }
    }

    public ActorResponseHandle SendRequest(ActorRequest request)
    {
        using var activity = ActivitySource.StartActivity(
            Tel.SpanNames.FormatRequestOperation(Tel.Operations.ProcessRequest));

        activity.SetupRequestOperation(this.ActorId, request.MessageId, request.Method, "ActorContext", "SendRequest");

        Log.SendRequestStarted(this._logger, this.ActorId.ToString(), request.MessageId);

        try
        {
            lock (this._lock)
            {
                string requestStatus;
                if (!this._inbox.TryGetValue(request.MessageId, out var entry))
                {
                    var requestMessage = new ActorRequestMessage(request.MessageId)
                    {
                        Method = request.Method,
                        Params = request.Params
                    };

                    entry = this._inbox[request.MessageId] = new(requestMessage);
                    this._pendingMessages.Writer.TryWrite(requestMessage);
                    Log.RequestMessageCreated(this._logger, this.ActorId.ToString(), request.MessageId, request.Method);
                    requestStatus = "created";
                }
                else
                {
                    Log.RequestMessageFound(this._logger, this.ActorId.ToString(), request.MessageId);
                    requestStatus = "found";
                }

                var handle = new InProcessActorResponseHandle(this, entry);
                Log.ResponseHandleCreated(this._logger, this.ActorId.ToString(), request.MessageId);

                activity.Complete(RequestCompleted, this.ActorId, [(Tel.Request.Status, requestStatus), (Tel.Response.Status, HandleCreated)],
                    (Tel.Message.Id, request.MessageId), (Tel.Message.Method, request.Method));

                return handle;
            }
        }
        catch (Exception ex)
        {
            activity.RecordFailure(ex, null, (Tel.Request.Status, "failed"));
            throw;
        }
    }

    public void OnProgressUpdate(string messageId, int sequenceNumber, JsonElement data)
    {
        using var activity = ActivitySource.StartActivity(
            Tel.SpanNames.FormatActorOperation(Tel.Operations.ProgressUpdate));

        activity.SetActorAttributes(this.ActorId);
        activity.SetMessageAttributes(messageId);
        activity?.SetTag(Tel.Message.SequenceNumber, sequenceNumber);

        try
        {
            Log.ProgressUpdateReceived(this._logger, this.ActorId.ToString(), messageId, sequenceNumber);
            var update = new UpdateRequestOperation(messageId, RequestStatus.Pending, data);
            this.PostRequestUpdate(update);

            activity.RecordSuccess((Tel.Message.Status, "processed"));
        }
        catch (Exception ex)
        {
            activity.RecordFailure(ex);
            throw;
        }
    }

    private void PostRequestUpdate(UpdateRequestOperation update)
    {
        lock (this._lock)
        {
            if (!this._inbox.TryGetValue(update.MessageId, out var entry))
            {
                Log.ProgressUpdateFailed(this._logger, this.ActorId.ToString(), update.MessageId, "Message not found in inbox");
                throw new InvalidOperationException($"Message with id '{update.MessageId}' not found while publishing update.");
            }

            entry.PostUpdate(update);
            if (update.Status is RequestStatus.Completed or RequestStatus.Failed)
            {
                entry.SetResponse(new ActorResponseMessage(update.MessageId)
                {
                    SenderId = this.ActorId,
                    Status = update.Status,
                    Data = update.Data
                });
            }

            Log.ProgressUpdatePublished(this._logger, this.ActorId.ToString(), update.MessageId);
        }
    }

    public async ValueTask<ReadResponse> ReadAsync(ActorReadOperationBatch operations, CancellationToken cancellationToken = default)
    {
        Log.ReadOperationStarted(this._logger, this.ActorId.ToString(), operations.Operations.Count);
        var result = await this.Storage.ReadStateAsync(
            this.ActorId,
            [.. operations.Operations.OfType<ActorStateReadOperation>()],
            cancellationToken).ConfigureAwait(false);
        Log.ReadOperationCompleted(this._logger, this.ActorId.ToString(), result.Results.Count);
        return result;
    }

    public async IAsyncEnumerable<ActorMessage> WatchMessagesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Log.WatchMessagesStarted(this._logger, this.ActorId.ToString());

        // TODO: Yield all pending requests - this likely requires reading the inbox from storage.
        // TODO: Yield all responses
        // TODO: Yield all updates
        var messageCount = 0;
        await foreach (var message in this._pendingMessages.Reader.ReadAllAsync(cancellationToken).ConfigureAwait(false))
        {
            messageCount++;
            var messageId = message switch
            {
                ActorRequestMessage requestMessage => requestMessage.MessageId,
                ActorResponseMessage responseMessage => responseMessage.MessageId,
                _ => "unknown"
            };
            Log.MessageYielded(this._logger, this.ActorId.ToString(), messageId, message.Type.ToString(), messageCount);
            yield return message;
        }

        Log.WatchMessagesCompleted(this._logger, this.ActorId.ToString(), messageCount);
    }

    public async ValueTask<WriteResponse> WriteAsync(ActorWriteOperationBatch operations, CancellationToken cancellationToken = default)
    {
        Log.WriteOperationStarted(this._logger, this.ActorId.ToString(), operations.Operations.Count);

        // TODO: Turn send & update message operations into storage writes to outbox

        IReadOnlyCollection<ActorStateWriteOperation> writeOps =
            [.. operations.Operations.OfType<ActorStateWriteOperation>()];

        WriteResponse result = await this.Storage.WriteStateAsync(
            this.ActorId,
            writeOps,
            operations.ETag,
            cancellationToken).ConfigureAwait(false);

        Log.WriteOperationCompleted(this._logger, this.ActorId.ToString(), result.Success);

        // Check if result success and schedule durable task to pump outbox if needed.
        if (result.Success)
        {
            var processedOperations = 0;
            foreach (var operation in operations.Operations)
            {
                if (operation is SendRequestOperation sendRequestOperation)
                {
                    Log.SendRequestOperationEncountered(this._logger, this.ActorId.ToString());
                    // Get the target actor from the runtime.
                    // Enqueue the request on the actor's inbox.
                    throw new NotImplementedException();
                }
                else if (operation is UpdateRequestOperation updateRequestOperation)
                {
                    Log.UpdateRequestOperationProcessing(this._logger, this.ActorId.ToString(), updateRequestOperation.MessageId);
                    // Find the request in this actor's inbox.
                    // Get the SenderId from the request.
                    // Get the sending actor from the runtime.
                    // Enqueue the request on the actor's inbox.
                    this.PostRequestUpdate(updateRequestOperation);
                    processedOperations++;
                }
            }
            Log.OperationProcessingCompleted(this._logger, this.ActorId.ToString(), processedOperations);
        }

        return result;
    }

    public async ValueTask DisposeAsync()
    {
        Log.ActorContextDisposing(this._logger, this.ActorId.ToString());

        this._cts.Dispose();
        await this._actorInstance.DisposeAsync().ConfigureAwait(false);
        if (this._actorRunTask is { } actorRunTask)
        {
            await actorRunTask.ConfigureAwait(false);
        }

        Log.ActorContextDisposed(this._logger, this.ActorId.ToString());
    }

    public void Dispose()
    {
        Log.ActorContextDisposing(this._logger, this.ActorId.ToString());

        this._cts.Dispose();
#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
        if (this._actorInstance is IDisposable actorInstanceDisposable)
        {
            actorInstanceDisposable.Dispose();
        }
        else
        {
            this._actorInstance.DisposeAsync().AsTask().GetAwaiter().GetResult();
        }

        this._actorRunTask?.GetAwaiter().GetResult();
#pragma warning restore VSTHRD002

        Log.ActorContextDisposed(this._logger, this.ActorId.ToString());
    }

    private sealed class ActorInboxEntry(ActorRequestMessage Request)
    {
        private readonly TaskCompletionSource<ActorResponseMessage> _responseTcs = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly Channel<UpdateRequestOperation> _updates = Channel.CreateUnbounded<UpdateRequestOperation>();
        public CancellationTokenSource Cts { get; } = new();
        public ActorRequestMessage Request { get; } = Request;
        public Task<ActorResponseMessage> Response => this._responseTcs.Task;

        public IAsyncEnumerable<UpdateRequestOperation> WatchUpdatesAsync(CancellationToken cancellationToken)
            => this._updates.Reader.ReadAllAsync(cancellationToken);

        public void PostUpdate(UpdateRequestOperation update)
        {
            if (!this._updates.Writer.TryWrite(update))
            {
                throw new InvalidOperationException("Failed to write update to the channel.");
            }
        }

        public void SetResponse(ActorResponseMessage response)
        {
            if (!this._responseTcs.TrySetResult(response))
            {
                throw new InvalidOperationException("Response has already been set.");
            }

            this._updates.Writer.TryComplete();
        }
    }

    private sealed class InProcessActorResponseHandle(InProcessActorContext context, ActorInboxEntry entry) : ActorResponseHandle
    {
#if NET8_0_OR_GREATER
        public override async ValueTask CancelAsync(CancellationToken cancellationToken) =>
            await entry.Cts.CancelAsync().ConfigureAwait(false);
#else
        public override ValueTask CancelAsync(CancellationToken cancellationToken)
        {
            entry.Cts.Cancel();
            return default;
        }
#endif

        public override async ValueTask<ActorResponse> GetResponseAsync(CancellationToken cancellationToken)
        {
            ActorResponse response;
            try
            {
                var responseMessage = await entry.Response
#if NET8_0_OR_GREATER
                    .WaitAsync(cancellationToken)
#endif
                    .ConfigureAwait(false);
                response = new ActorResponse
                {
                    ActorId = context.ActorId,
                    MessageId = entry.Request.MessageId,
                    Data = responseMessage.Data,
                    Status = responseMessage.Status,
                };
            }
            catch (Exception exception)
            {
                response = new ActorResponse
                {
                    ActorId = context.ActorId,
                    MessageId = entry.Request.MessageId,
                    Data = JsonSerializer.SerializeToElement($"Error: {exception.Message}", AgentRuntimeJsonUtilities.JsonContext.Default.String),
                    Status = RequestStatus.Failed,
                };
            }

            return response;
        }

        public override bool TryGetResponse([NotNullWhen(true)] out ActorResponse? response)
        {
            if (entry.Response.Status is TaskStatus.RanToCompletion)
            {
#pragma warning disable VSTHRD002 // Avoid problematic synchronous waits
                var responseMessage = entry.Response.Result;
#pragma warning restore VSTHRD002
                response = new ActorResponse
                {
                    ActorId = context.ActorId,
                    MessageId = entry.Request.MessageId,
                    Data = responseMessage.Data,
                    Status = responseMessage.Status,
                };

                return true;
            }

            response = null;
            return false;
        }

        public override async IAsyncEnumerable<ActorRequestUpdate> WatchUpdatesAsync([EnumeratorCancellation] CancellationToken cancellationToken)
        {
            await foreach (var update in entry.WatchUpdatesAsync(cancellationToken).ConfigureAwait(false))
            {
                yield return new ActorRequestUpdate(update.Status, update.Data);
            }

            var response = await entry.Response
#if NET8_0_OR_GREATER
                .WaitAsync(cancellationToken)
#endif
                .ConfigureAwait(false);
            yield return new ActorRequestUpdate(response.Status, response.Data);
        }
    }
}
