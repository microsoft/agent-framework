// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Models;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.Caching.Memory;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// In-memory implementation of responses service for testing and development.
/// This implementation is thread-safe but data is not persisted across application restarts.
/// </summary>
internal sealed class InMemoryResponsesService : IResponsesService, IDisposable
{
    private readonly IResponseExecutor _executor;
    private readonly MemoryCache _cache;
    private readonly InMemoryStorageOptions _options;
    private readonly Conversations.IConversationStorage? _conversationStorage;

    private sealed class ResponseState
    {
        private readonly object _lock = new();
        private TaskCompletionSource _updateSignal = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly Dictionary<int, ItemResource> _outputItems = [];

        public Response? Response { get; set; }
        public CreateResponse? Request { get; set; }
        public List<StreamingResponseEvent> StreamingUpdates { get; } = [];
        public Task? CompletionTask { get; set; }
        public CancellationTokenSource? CancellationTokenSource { get; set; }
        public bool IsTerminal => this.Response?.IsTerminal ?? false;

        public void AddStreamingEvent(StreamingResponseEvent streamingEvent)
        {
            lock (this._lock)
            {
                this.StreamingUpdates.Add(streamingEvent);

                // Update the response object for events that contain it
                if (streamingEvent is IStreamingResponseEventWithResponse responseEvent)
                {
                    this.Response = responseEvent.Response;
                }

                // Track output items as they're added or updated
                if (streamingEvent is StreamingOutputItemAdded itemAdded)
                {
                    this._outputItems[itemAdded.OutputIndex] = itemAdded.Item;
                    this.UpdateResponseOutput();
                }
                else if (streamingEvent is StreamingOutputItemDone itemDone)
                {
                    this._outputItems[itemDone.OutputIndex] = itemDone.Item;
                    this.UpdateResponseOutput();
                }
            }

            this.SignalUpdate();
        }

        private void UpdateResponseOutput()
        {
            // Update the Response.Output list with current items
            if (this.Response is not null)
            {
                List<ItemResource> outputList = [.. this._outputItems.OrderBy(kvp => kvp.Key).Select(kvp => kvp.Value)];
                this.Response = this.Response with { Output = outputList };
            }
        }

        public async IAsyncEnumerable<StreamingResponseEvent> StreamUpdatesAsync(
            int startingAfter = 0,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            int streamedCount = startingAfter;
            while (true)
            {
                cancellationToken.ThrowIfCancellationRequested();

                // Capture the wait task before checking state to avoid race conditions
                Task waitTask = this.WaitForUpdateAsync(cancellationToken);

                // Copy any new updates and check terminal state while holding the lock
                List<StreamingResponseEvent> newUpdates;
                bool isTerminal;
                lock (this._lock)
                {
                    newUpdates = this.StreamingUpdates.Skip(streamedCount).ToList();
                    streamedCount += newUpdates.Count;
                    isTerminal = this.IsTerminal;
                }

                // Yield the updates outside the lock
                foreach (StreamingResponseEvent update in newUpdates)
                {
                    yield return update;
                }

                // Check if we're done (after yielding any final events)
                if (isTerminal)
                {
                    break;
                }

                // Wait for the next update to be signaled
                await waitTask.ConfigureAwait(false);
            }
        }

        private Task WaitForUpdateAsync(CancellationToken cancellationToken)
        {
            Task signalTask = this._updateSignal.Task;
            return signalTask.WaitAsync(cancellationToken);
        }

        internal void SignalUpdate()
        {
            TaskCompletionSource oldSignal = Interlocked.Exchange(ref this._updateSignal, new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously));
            oldSignal.TrySetResult();
        }
    }

    public InMemoryResponsesService(IResponseExecutor executor)
        : this(executor, new InMemoryStorageOptions(), null)
    {
    }

    public InMemoryResponsesService(IResponseExecutor executor, InMemoryStorageOptions options)
        : this(executor, options, null)
    {
    }

    public InMemoryResponsesService(IResponseExecutor executor, InMemoryStorageOptions options, Conversations.IConversationStorage? conversationStorage)
    {
        ArgumentNullException.ThrowIfNull(executor);
        ArgumentNullException.ThrowIfNull(options);
        this._executor = executor;
        this._options = options;
        this._cache = new MemoryCache(options.ToMemoryCacheOptions());
        this._conversationStorage = conversationStorage;
    }

    public async ValueTask<ResponseError?> ValidateRequestAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default)
    {
        if (request.Conversation is not null && !string.IsNullOrEmpty(request.Conversation.Id) &&
            !string.IsNullOrEmpty(request.PreviousResponseId))
        {
            return new ResponseError
            {
                Code = "invalid_request",
                Message = "Mutually exclusive parameters: 'conversation' and 'previous_response_id'. Ensure you are only providing one of: 'previous_response_id' or 'conversation'."
            };
        }

        return await this._executor.ValidateRequestAsync(request, cancellationToken).ConfigureAwait(false);
    }

    public async Task<Response> CreateResponseAsync(
        CreateResponse request,
        CancellationToken cancellationToken = default)
    {
        if (request.Stream == true)
        {
            throw new InvalidOperationException("Cannot create a streaming response using CreateResponseAsync. Use CreateResponseStreamingAsync instead.");
        }

        var idGenerator = new IdGenerator(responseId: null, conversationId: request.Conversation?.Id);
        var responseId = idGenerator.ResponseId;
        var state = this.InitializeResponse(responseId, request);
        var ct = request.Background switch
        {
            true => CancellationToken.None,
            _ => cancellationToken,
        };
        state.CompletionTask = this.ExecuteResponseAsync(responseId, state, ct);

        // For background responses, start execution and return immediately
        if (request.Background == true)
        {
            return state.Response!;
        }

        // For non-background responses, wait for completion
        await state.CompletionTask!.WaitAsync(cancellationToken).ConfigureAwait(false);
        return state.Response!;
    }

    public async IAsyncEnumerable<StreamingResponseEvent> CreateResponseStreamingAsync(
        CreateResponse request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (request.Stream == false)
        {
            throw new InvalidOperationException("Cannot create a non-streaming response using CreateResponseStreamingAsync. Use CreateResponseAsync instead.");
        }

        var idGenerator = new IdGenerator(responseId: null, conversationId: request.Conversation?.Id);
        var responseId = idGenerator.ResponseId;
        var state = this.InitializeResponse(responseId, request);

        // Start execution
        state.CompletionTask = this.ExecuteResponseAsync(responseId, state, CancellationToken.None);

        // Stream updates as they become available
        await foreach (StreamingResponseEvent update in state.StreamUpdatesAsync(cancellationToken: cancellationToken).ConfigureAwait(false))
        {
            yield return update;
        }
    }

    public Task<Response?> GetResponseAsync(string responseId, CancellationToken cancellationToken = default)
    {
        this._cache.TryGetValue(responseId, out ResponseState? state);
        return Task.FromResult(state?.Response);
    }

    public async IAsyncEnumerable<StreamingResponseEvent> GetResponseStreamingAsync(
        string responseId,
        int? startingAfter = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (!this._cache.TryGetValue(responseId, out ResponseState? state) || state is null)
        {
            yield break;
        }

        // Stream existing updates starting from the specified position
        await foreach (StreamingResponseEvent update in state.StreamUpdatesAsync(startingAfter ?? 0, cancellationToken).ConfigureAwait(false))
        {
            yield return update;
        }
    }

    public async Task<Response> CancelResponseAsync(string responseId, CancellationToken cancellationToken = default)
    {
        if (!this._cache.TryGetValue(responseId, out ResponseState? state) || state is null)
        {
            throw new InvalidOperationException($"Response '{responseId}' not found.");
        }

        if (state.Response is null || state.Response.Background != true)
        {
            throw new InvalidOperationException($"Only background responses can be cancelled. Response '{responseId}' was not created with background=true.");
        }

        if (state.IsTerminal)
        {
            throw new InvalidOperationException($"Response '{responseId}' is already in a terminal state and cannot be cancelled.");
        }

        // Cancel the execution
        state.CancellationTokenSource?.Cancel();

        if (state.CompletionTask is { } task)
        {
            await task.WaitAsync(cancellationToken).ConfigureAwait(ConfigureAwaitOptions.SuppressThrowing);
        }

        return state.Response;
    }

    public Task<bool> DeleteResponseAsync(string responseId, CancellationToken cancellationToken = default)
    {
        if (!this._cache.TryGetValue(responseId, out ResponseState? state))
        {
            return Task.FromResult(false);
        }

        // Cancel any ongoing execution
        state?.CancellationTokenSource?.Cancel();

        // Remove the response
        this._cache.Remove(responseId);
        return Task.FromResult(true);
    }

    public Task<ListResponse<ItemResource>> ListResponseInputItemsAsync(
        string responseId,
        int? limit = null,
        SortOrder? order = null,
        string? after = null,
        string? before = null,
        CancellationToken cancellationToken = default)
    {
        int effectiveLimit = Math.Clamp(limit ?? IResponsesService.DefaultListLimit, 1, 100);
        SortOrder effectiveOrder = order ?? SortOrder.Descending;

        if (!this._cache.TryGetValue(responseId, out ResponseState? state))
        {
            throw new InvalidOperationException($"Response '{responseId}' not found.");
        }

        if (state is null)
        {
            throw new InvalidOperationException($"Response '{responseId}' state is null.");
        }

        var itemResources = GetInputItems(responseId, state);

        // Apply ordering
        if (effectiveOrder == SortOrder.Descending)
        {
            itemResources.Reverse();
        }

        // Apply pagination
        var filtered = itemResources.AsEnumerable();

        if (!string.IsNullOrEmpty(after))
        {
            int afterIndex = itemResources.FindIndex(m => m.Id == after);
            if (afterIndex >= 0)
            {
                filtered = itemResources.Skip(afterIndex + 1);
            }
        }

        if (!string.IsNullOrEmpty(before))
        {
            int beforeIndex = itemResources.FindIndex(m => m.Id == before);
            if (beforeIndex >= 0)
            {
                filtered = filtered.Take(beforeIndex);
            }
        }

        var result = filtered.Take(effectiveLimit + 1).ToList();
        var hasMore = result.Count > effectiveLimit;
        if (hasMore)
        {
            result = result.Take(effectiveLimit).ToList();
        }

        return Task.FromResult(new ListResponse<ItemResource>
        {
            Data = result,
            FirstId = result.FirstOrDefault()?.Id,
            LastId = result.LastOrDefault()?.Id,
            HasMore = hasMore
        });
    }

    private ResponseState InitializeResponse(string responseId, CreateResponse request)
    {
        var metadata = request.Metadata ?? [];

        // Create initial response
        // Background responses always start as "queued", non-background as "in_progress"
        var initialStatus = request.Background is true ? ResponseStatus.Queued : ResponseStatus.InProgress;
        var response = new Response
        {
            Agent = request.Agent?.ToAgentId(),
            Background = request.Background,
            Conversation = request.Conversation,
            CreatedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            Error = null,
            Id = responseId,
            IncompleteDetails = null,
            Instructions = request.Instructions,
            MaxOutputTokens = request.MaxOutputTokens,
            MaxToolCalls = request.MaxToolCalls,
            Metadata = metadata,
            Model = request.Model,
            Output = [],
            ParallelToolCalls = request.ParallelToolCalls ?? true,
            PreviousResponseId = request.PreviousResponseId,
            Prompt = request.Prompt,
            PromptCacheKey = request.PromptCacheKey,
            Reasoning = request.Reasoning,
            SafetyIdentifier = request.SafetyIdentifier,
            ServiceTier = request.ServiceTier,
            Status = initialStatus,
            Store = request.Store,
            Temperature = request.Temperature,
            Text = request.Text,
            ToolChoice = request.ToolChoice,
            Tools = [.. request.Tools ?? []],
            TopLogprobs = request.TopLogprobs,
            TopP = request.TopP,
            Truncation = request.Truncation,
            Usage = ResponseUsage.Zero,
#pragma warning disable CS0618 // Type or member is obsolete
            User = request.User
#pragma warning restore CS0618 // Type or member is obsolete
        };

        var state = new ResponseState
        {
            Response = response,
            Request = request,
            CancellationTokenSource = new CancellationTokenSource()
        };

        var entryOptions = this._options.ToMemoryCacheEntryOptions();
        entryOptions.RegisterPostEvictionCallback((key, value, reason, state) =>
        {
            if (value is ResponseState responseState)
            {
                responseState.CancellationTokenSource?.Cancel();
            }
        });

        this._cache.Set(responseId, state, entryOptions);

        return state;
    }

    private async Task ExecuteResponseAsync(string responseId, ResponseState state, CancellationToken cancellationToken)
    {
        await Task.CompletedTask.ConfigureAwait(ConfigureAwaitOptions.ForceYielding);
        var request = state.Request!;
        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, state.CancellationTokenSource!.Token);

        try
        {
            // Create agent invocation context
            var context = new AgentInvocationContext(new IdGenerator(responseId: responseId, conversationId: state.Response?.Conversation?.Id));

            // Collect output items for conversation storage
            List<ItemResource> outputItems = [];

            // Execute using the injected executor
            await foreach (var streamingEvent in this._executor.ExecuteAsync(context, request, linkedCts.Token).ConfigureAwait(false))
            {
                state.AddStreamingEvent(streamingEvent);

                // Collect output items
                if (streamingEvent is StreamingOutputItemDone itemDone)
                {
                    outputItems.Add(itemDone.Item);
                }
            }

            // Add both input and output items to conversation storage if available
            // This happens AFTER successful execution, in line with OpenAI's behavior
            if (this._conversationStorage is not null && request.Conversation?.Id is not null)
            {
                var inputItems = GetInputItems(responseId, state);
                var allItems = new List<ItemResource>(inputItems.Count + outputItems.Count);
                allItems.AddRange(inputItems);
                allItems.AddRange(outputItems);

                if (allItems.Count > 0)
                {
                    await this._conversationStorage.AddItemsAsync(request.Conversation.Id, allItems, linkedCts.Token).ConfigureAwait(false);
                }
            }

            // Update response status to completed if not already in a terminal state
            if (!state.IsTerminal)
            {
                state.Response = state.Response! with
                {
                    Status = ResponseStatus.Completed
                };

                var sequenceNumber = state.StreamingUpdates.Count + 1;
                var completedEvent = new StreamingResponseCompleted
                {
                    SequenceNumber = sequenceNumber,
                    Response = state.Response
                };

                state.AddStreamingEvent(completedEvent);
            }
        }
        catch (OperationCanceledException)
        {
            // Update response status to cancelled
            state.Response = state.Response! with
            {
                Status = ResponseStatus.Cancelled
            };

            var sequenceNumber = state.StreamingUpdates.Count + 1;
            var cancelledEvent = new StreamingResponseCancelled
            {
                SequenceNumber = sequenceNumber,
                Response = state.Response
            };

            state.AddStreamingEvent(cancelledEvent);
        }
        catch (Exception ex)
        {
            // Update response status to failed
            state.Response = state.Response! with
            {
                Status = ResponseStatus.Failed,
                Error = new ResponseError
                {
                    Code = "execution_error",
                    Message = ex.Message
                }
            };

            var sequenceNumber = state.StreamingUpdates.Count + 1;
            var failedEvent = new StreamingResponseFailed
            {
                SequenceNumber = sequenceNumber,
                Response = state.Response
            };

            state.AddStreamingEvent(failedEvent);
        }
        finally
        {
            // Signal one final time to unblock any waiting consumers
            state.SignalUpdate();
        }
    }

    private static List<ItemResource> GetInputItems(string responseId, ResponseState state)
    {
        var itemResources = new List<ItemResource>();
        if (state.Request is not null)
        {
            // Use a deterministic random seed. We add 1 to avoid clashing with the output message ids.
            var randomSeed = responseId.GetHashCode() + 1;
            var idGenerator = new IdGenerator(responseId: responseId, conversationId: state.Response?.Conversation?.Id, randomSeed: randomSeed);
            foreach (var inputMessage in state.Request.Input.GetInputMessages())
            {
                itemResources.AddRange(inputMessage.ToItemResource(idGenerator));
            }
        }

        return itemResources;
    }

    public void Dispose()
    {
        this._cache.Dispose();
    }
}
