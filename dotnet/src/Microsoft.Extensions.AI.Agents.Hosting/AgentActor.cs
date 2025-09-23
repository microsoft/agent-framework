// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;

namespace Microsoft.Extensions.AI.Agents.Hosting;

internal sealed class AgentActor(
    AIAgent agent,
    IActorRuntimeContext context,
    ILogger<AgentActor> logger) : IActor
{
    private const string ThreadStateKey = "thread";
    private string? _etag;
    private AgentThread? _thread;

    public ValueTask DisposeAsync() => default;

    public async ValueTask RunAsync(CancellationToken cancellationToken)
    {
        Log.ActorStarted(logger, context.ActorId.ToString(), agent.Name ?? "Unknown");
        await Task.Yield();

        // Restore thread state
        var response = await context.ReadAsync(
            new ActorReadOperationBatch([new GetValueOperation(ThreadStateKey)]),
            cancellationToken).ConfigureAwait(false);

        this._etag = response.ETag;
        var hasExistingThread = false;
        if (response.Results[0] is GetValueResult { Value: { } threadJson })
        {
            // Deserialize the thread state if it exists
            this._thread = agent.DeserializeThread(threadJson);
            hasExistingThread = true;
        }

        this._thread ??= agent.GetNewThread();
        Log.ThreadStateRestored(logger, context.ActorId.ToString(), hasExistingThread);

        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                await foreach (var message in context.WatchMessagesAsync(cancellationToken).ConfigureAwait(false))
                {
                    switch (message.Type)
                    {
                        case ActorMessageType.Request:
                            await this.HandleAgentRequestAsync((ActorRequestMessage)message, cancellationToken).ConfigureAwait(false);
                            break;
                        case ActorMessageType.Response:
                            // Handle response messages if needed
                            break;
                        default:
                            Log.UnknownMessageType(logger, message.Type.ToString(), context.ActorId.ToString());
                            break;
                    }
                }
            }
            catch (Exception ex)
            {
                if (cancellationToken.IsCancellationRequested && ex is OperationCanceledException)
                {
                    return;
                }

                Log.ErrorProcessingMessages(logger, ex, context.ActorId.ToString());
            }
        }
    }

    private async Task HandleAgentRequestAsync(ActorRequestMessage message, CancellationToken cancellationToken)
    {
        var requestId = message.MessageId;
        Debug.Assert(this._thread is not null);
        Debug.Assert(this._etag is not null);

        if (message.Method is not AgentActorConstants.RunMethodName)
        {
            // Unsupported method, we can only handle "Run" requests.
            var data = JsonSerializer.SerializeToElement("Unsupported method.", AgentHostingJsonUtilities.DefaultOptions.GetTypeInfo(typeof(string)));
            await context.WriteAsync(
                new(this._etag, [
                    new UpdateRequestOperation(
                        requestId,
                        RequestStatus.Failed,
                        data)]),
                cancellationToken).ConfigureAwait(false);
            return;
        }

        // Parse the request to get the agent run parameters
        List<ChatMessage>? messages;
        if (message.Params is { } payload)
        {
            var arg = payload.Deserialize(AgentHostingJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunRequest))) as AgentRunRequest;
            messages = arg?.Messages;
        }

        messages ??= [];

        Log.ProcessingAgentRequest(logger, requestId, context.ActorId.ToString(), messages.Count);
        try
        {
            var i = 0;
            var updates = new List<AgentRunResponseUpdate>();
            await foreach (var update in agent.RunStreamingAsync(messages, this._thread, cancellationToken: cancellationToken).ConfigureAwait(false))
            {
                var updateJson = JsonSerializer.SerializeToElement(update, AIJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponseUpdate)));
                context.OnProgressUpdate(requestId, i++, updateJson);
                updates.Add(update);
                Log.AgentStreamingUpdate(logger, requestId, i);
            }

            var serializedRunResponse = JsonSerializer.SerializeToElement(updates.ToAgentRunResponse(), AIJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AgentRunResponse)));
            var updatedThread = await this._thread.SerializeAsync(AgentHostingJsonUtilities.DefaultOptions, cancellationToken).ConfigureAwait(false);

            var writeResponse = await context.WriteAsync(
                new(this._etag,
                [
                    new UpdateRequestOperation(requestId, RequestStatus.Completed, serializedRunResponse),
                    new SetValueOperation(ThreadStateKey, updatedThread)
                ]), cancellationToken)
                .ConfigureAwait(false);
            if (!writeResponse.Success)
            {
                Log.WriteOperationFailed(logger, context.ActorId.ToString(), requestId);
            }
            else
            {
                Log.AgentRequestCompleted(logger, requestId, updates.Count);
            }

            this._etag = writeResponse.ETag;
        }
        catch (Exception exception)
        {
            Log.AgentRequestFailed(logger, exception, requestId, context.ActorId.ToString());

            // TODO: Retry later?
        }
    }
}
