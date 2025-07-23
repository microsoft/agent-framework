// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using HelloHttpApi.ApiService;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;

internal sealed class ChatClientAgentActor(AIAgent agent, JsonSerializerOptions jsonSerializerOptions, IActorRuntimeContext context, ILogger<ChatClientAgentActor> logger) : IActor
{
    private string? _etag;
    private ChatClientAgentThread? _thread;

    public ValueTask DisposeAsync() => default;

    public async ValueTask RunAsync(CancellationToken cancellationToken)
    {
        Log.ActorStarted(logger, context.ActorId.ToString(), agent.Name ?? "Unknown");
        await Task.Yield();

        // Restore thread state
        var response = await context.ReadAsync(
            new ActorReadOperationBatch([new GetValueOperation("thread")]),
            cancellationToken).ConfigureAwait(false);

        this._etag = response.ETag;
        if (response.Results[0] is GetValueResult threadResult)
        {
            if (threadResult.Value is { } threadJson)
            {
                // Deserialize the thread state if it exist
                this._thread = threadJson.Deserialize<ChatClientAgentThread>(
                    (JsonTypeInfo<ChatClientAgentThread>)jsonSerializerOptions.GetTypeInfo(typeof(ChatClientAgentThread)));
            }
        }

        this._thread ??= agent.GetNewThread() as ChatClientAgentThread ?? throw new InvalidOperationException("The agent did not provide a valid thread instance.");
        Log.ThreadStateRestored(logger, context.ActorId.ToString(), response.Results[0] is GetValueResult { Value: not null });

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
                Log.ErrorProcessingMessages(logger, ex, context.ActorId.ToString());
            }
        }
    }

    private async Task HandleAgentRequestAsync(ActorRequestMessage message, CancellationToken cancellationToken)
    {
        var requestId = message.MessageId;
        Debug.Assert(this._thread is not null);
        Debug.Assert(this._etag is not null);

        // Parse the request to get the agent run parameters
        List<ChatMessage>? messages;
        if (message.Params is { } payload)
        {
            var arg = payload.Deserialize<ChatClientAgentRunRequest>(
                (JsonTypeInfo<ChatClientAgentRunRequest>)jsonSerializerOptions.GetTypeInfo(typeof(ChatClientAgentRunRequest)));
            messages = arg?.Messages;
        }

        messages ??= [];

        Log.ProcessingAgentRequest(logger, requestId, context.ActorId.ToString(), messages.Count);
        try
        {
            var typeInfo = (JsonTypeInfo<AgentRunResponseUpdate>)jsonSerializerOptions.GetTypeInfo(typeof(AgentRunResponseUpdate));
            var i = 0;
            var updates = new List<AgentRunResponseUpdate>();
            await foreach (var update in agent.RunStreamingAsync(messages, this._thread, cancellationToken: cancellationToken).ConfigureAwait(false))
            {
                var updateJson = JsonSerializer.SerializeToElement(update, typeInfo);
                context.OnProgressUpdate(requestId, i++, updateJson);
                updates.Add(update);
                Log.AgentStreamingUpdate(logger, requestId, i);
            }

            var serializedRunResponse = JsonSerializer.SerializeToElement(
                updates.ToAgentRunResponse(),
                (JsonTypeInfo<AgentRunResponse>)jsonSerializerOptions.GetTypeInfo(typeof(AgentRunResponse)));
            var writeResponse = await context.WriteAsync(
                new(this._etag, [new UpdateRequestOperation(requestId, RequestStatus.Completed, serializedRunResponse)]), cancellationToken)
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
