// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using System.Threading.Tasks.Sources;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Caching.Memory;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests publication and consumption of stored response events.
/// </summary>
public sealed class InMemoryResponsesServiceStreamingTests
{
    private static readonly TimeSpan s_timeout = TimeSpan.FromSeconds(10);

    [Theory]
    [InlineData("completed")]
    [InlineData("failed")]
    [InlineData("cancelled")]
    public async Task SynthesizedTerminalEvent_IsPublishedWithResponseAsync(string outcome)
    {
        // Arrange
        var executor = new ControlledResponseExecutor();
        using var service = new InMemoryResponsesService(executor);
        using var timeout = new CancellationTokenSource(s_timeout);
        Response response = await service.CreateResponseAsync(new CreateResponse
        {
            Input = ResponseInput.FromText("hello"),
            Background = true
        }, timeout.Token);
        await executor.ContinuationRegistered.Task.WaitAsync(timeout.Token);

        // Observe the private publication lock without introducing a production test hook.
        var cache = (IMemoryCache)typeof(InMemoryResponsesService)
            .GetField("_cache", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(service)!;
        Assert.True(cache.TryGetValue(response.Id, out object? state));
        Assert.NotNull(state);
        object syncRoot = state.GetType().GetField("_lock", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(state)!;
        await using IAsyncEnumerator<StreamingResponseEvent> reader = service.GetResponseStreamingAsync(response.Id)
            .GetAsyncEnumerator(timeout.Token);
        var producer = new Thread(() => executor.Complete(outcome)) { IsBackground = true };
        Task<bool>? moveNext = null;
        bool completedBeforePublication = false;

        // Act
        try
        {
            lock (syncRoot)
            {
                producer.Start();

                // The registered continuation runs inline on this dedicated thread. After disposing
                // the executor, its only blocking operation is acquiring the publication lock.
                Assert.True(SpinWait.SpinUntil(
                    () => executor.DisposalThreadId == producer.ManagedThreadId &&
                        (producer.ThreadState & ThreadState.WaitSleepJoin) != 0,
                    s_timeout));
                Assert.Equal(producer.ManagedThreadId, executor.ContinuationThreadId);

                // Reenter the same monitor as a reader. Until the producer can append its event,
                // a reader must remain pending rather than observe terminal state and stop.
                moveNext = reader.MoveNextAsync().AsTask();
                completedBeforePublication = moveNext.IsCompleted;
            }
        }
        finally
        {
            Assert.True(producer.Join(s_timeout));
        }

        // Assert
        Assert.NotNull(moveNext);
        Assert.True(await moveNext.WaitAsync(timeout.Token));
        Assert.False(completedBeforePublication);
        Assert.Equal($"response.{outcome}", reader.Current.Type);
        var terminal = Assert.IsAssignableFrom<IStreamingResponseEventWithResponse>(reader.Current);
        Assert.True(terminal.Response.IsTerminal);
        Assert.Same(terminal.Response, await service.GetResponseAsync(response.Id, timeout.Token));
        Assert.False(await reader.MoveNextAsync());
    }

    [Theory]
    [InlineData("completed")]
    [InlineData("failed")]
    [InlineData("cancelled")]
    public async Task SynthesizedTerminalEvent_PreservesOutputForReadersAndReplayAsync(string outcome)
    {
        // Arrange
        var output = new ResponsesAssistantMessageItemResource
        {
            Id = "msg_partial",
            Status = ResponsesMessageItemResourceStatus.InProgress,
            Content = [new ItemContentOutputText { Text = "Partial output", Annotations = [] }]
        };
        var outputEvent = new StreamingOutputItemAdded { SequenceNumber = 1, OutputIndex = 0, Item = output };
        var executor = new ControlledResponseExecutor((_, _) => [outputEvent]);
        using var service = new InMemoryResponsesService(executor);
        using var timeout = new CancellationTokenSource(s_timeout);
        Response response = await service.CreateResponseAsync(new CreateResponse
        {
            Input = ResponseInput.FromText("hello"),
            Background = true
        }, timeout.Token);
        await executor.ContinuationRegistered.Task.WaitAsync(timeout.Token);
        await using IAsyncEnumerator<StreamingResponseEvent> first = service.GetResponseStreamingAsync(response.Id)
            .GetAsyncEnumerator(timeout.Token);
        await using IAsyncEnumerator<StreamingResponseEvent> second = service.GetResponseStreamingAsync(response.Id)
            .GetAsyncEnumerator(timeout.Token);
        Task<bool> firstMove;
        Task<bool> secondMove;
        bool firstCompletedBeforePublication;
        bool secondCompletedBeforePublication;
        Task<Response>? cancellation = null;
        bool executionCancellationRequested = false;
        bool cancellationCompletedBeforePublication = false;
        try
        {
            Assert.True(await first.MoveNextAsync());
            Assert.True(await second.MoveNextAsync());
            Assert.Same(outputEvent, first.Current);
            Assert.Same(outputEvent, second.Current);
            firstMove = first.MoveNextAsync().AsTask();
            secondMove = second.MoveNextAsync().AsTask();
            firstCompletedBeforePublication = firstMove.IsCompleted;
            secondCompletedBeforePublication = secondMove.IsCompleted;

            // Act
            if (outcome == "cancelled")
            {
                cancellation = service.CancelResponseAsync(response.Id, timeout.Token);
                executionCancellationRequested = executor.ExecutionCancellationToken.IsCancellationRequested;
                cancellationCompletedBeforePublication = cancellation.IsCompleted;
            }
        }
        finally
        {
            executor.Complete(outcome);
        }

        // Settle both moves before asserting their earlier state so a failed assertion cannot
        // dispose an iterator while MoveNextAsync is still pending.
        bool[] receivedTerminal = await Task.WhenAll(firstMove, secondMove).WaitAsync(timeout.Token);

        // Assert
        Assert.False(firstCompletedBeforePublication);
        Assert.False(secondCompletedBeforePublication);
        Assert.All(receivedTerminal, Assert.True);
        if (cancellation is not null)
        {
            Assert.True(executionCancellationRequested);
            Assert.False(cancellationCompletedBeforePublication);
        }

        StreamingResponseEvent terminalEvent = first.Current;
        Assert.Same(terminalEvent, second.Current);
        Assert.Equal($"response.{outcome}", terminalEvent.Type);
        Assert.Equal(2, terminalEvent.SequenceNumber);
        var terminal = Assert.IsAssignableFrom<IStreamingResponseEventWithResponse>(terminalEvent);
        Assert.Same(output, Assert.Single(terminal.Response.Output));
        Assert.Same(terminal.Response, await service.GetResponseAsync(response.Id, timeout.Token));
        if (outcome == "failed")
        {
            Assert.NotNull(terminal.Response.Error);
            Assert.Equal("execution_error", terminal.Response.Error.Code);
            Assert.Equal("Test executor failure.", terminal.Response.Error.Message);
        }

        if (cancellation is not null)
        {
            Assert.Same(terminal.Response, await cancellation.WaitAsync(timeout.Token));
        }

        Assert.False(await first.MoveNextAsync());
        Assert.False(await second.MoveNextAsync());
        List<StreamingResponseEvent> replay = await ReadEventsAsync(service.GetResponseStreamingAsync(response.Id), timeout.Token);
        Assert.Collection(replay, item => Assert.Same(outputEvent, item), item => Assert.Same(terminalEvent, item));
        List<StreamingResponseEvent> resumed = await ReadEventsAsync(
            service.GetResponseStreamingAsync(response.Id, startingAfter: 1), timeout.Token);
        Assert.Same(terminalEvent, Assert.Single(resumed));
    }

    [Fact]
    public async Task CreateResponseStreamingAsync_CancelledReader_DoesNotCancelProducerOrOtherReaderAsync()
    {
        // Arrange
        var executor = new ControlledResponseExecutor();
        using var service = new InMemoryResponsesService(executor);
        using var timeout = new CancellationTokenSource(s_timeout);
        using var readerCancellation = new CancellationTokenSource();
        await using IAsyncEnumerator<StreamingResponseEvent> cancelledReader = service.CreateResponseStreamingAsync(new CreateResponse
        {
            Input = ResponseInput.FromText("hello"),
            Stream = true
        }).GetAsyncEnumerator(readerCancellation.Token);
        Task<bool> cancelledMove = cancelledReader.MoveNextAsync().AsTask();
        await executor.ContinuationRegistered.Task.WaitAsync(timeout.Token);
        await using IAsyncEnumerator<StreamingResponseEvent> otherReader = service.GetResponseStreamingAsync(executor.ResponseId)
            .GetAsyncEnumerator(timeout.Token);
        Task<bool> otherMove = otherReader.MoveNextAsync().AsTask();

        // Act
        Exception? cancellationException;
        bool executionCancellationRequested;
        bool otherCompletedBeforePublication;
        try
        {
            readerCancellation.Cancel();
            cancellationException = await Record.ExceptionAsync(() => cancelledMove.WaitAsync(timeout.Token));
            executionCancellationRequested = executor.ExecutionCancellationToken.IsCancellationRequested;
            otherCompletedBeforePublication = otherMove.IsCompleted;
        }
        finally
        {
            executor.Complete("completed");
        }

        bool receivedTerminal = await otherMove.WaitAsync(timeout.Token);

        // Assert
        Assert.IsAssignableFrom<OperationCanceledException>(cancellationException);
        Assert.False(executionCancellationRequested);
        Assert.False(otherCompletedBeforePublication);
        Assert.True(receivedTerminal);
        StreamingResponseEvent terminalEvent = otherReader.Current;
        Assert.IsType<StreamingResponseCompleted>(terminalEvent);
        Assert.False(await otherReader.MoveNextAsync());
        List<StreamingResponseEvent> replay = await ReadEventsAsync(service.GetResponseStreamingAsync(executor.ResponseId), timeout.Token);
        Assert.Same(terminalEvent, Assert.Single(replay));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task ExecutorTerminalEvent_IsPreservedWithoutSynthesizedCompletionAsync(bool incomplete)
    {
        // Arrange
        StreamingResponseEvent? suppliedEvent = null;
        var executor = new ControlledResponseExecutor((context, request) =>
        {
            var response = new Response
            {
                Id = context.ResponseId,
                CreatedAt = 123,
                Background = request.Background,
                Status = incomplete ? ResponseStatus.Incomplete : ResponseStatus.Completed,
                Output = [],
                Usage = ResponseUsage.Zero,
                Tools = []
            };
            suppliedEvent = incomplete
                ? new StreamingResponseIncomplete { SequenceNumber = 42, Response = response }
                : new StreamingResponseCompleted { SequenceNumber = 42, Response = response };
            return [suppliedEvent];
        });
        using var service = new InMemoryResponsesService(executor);
        using var timeout = new CancellationTokenSource(s_timeout);
        Response initialResponse = await service.CreateResponseAsync(new CreateResponse
        {
            Input = ResponseInput.FromText("hello"),
            Background = true
        }, timeout.Token);
        await executor.ContinuationRegistered.Task.WaitAsync(timeout.Token);

        // Act
        List<StreamingResponseEvent> initial;
        try
        {
            initial = await ReadEventsAsync(service.GetResponseStreamingAsync(initialResponse.Id), timeout.Token);
        }
        finally
        {
            executor.Complete("completed");
        }

        List<StreamingResponseEvent> replay = await ReadEventsAsync(service.GetResponseStreamingAsync(initialResponse.Id), timeout.Token);

        // Assert
        Assert.Same(suppliedEvent, Assert.Single(initial));
        Assert.Same(suppliedEvent, Assert.Single(replay));
        Assert.NotNull(suppliedEvent);
        Assert.Equal(42, suppliedEvent.SequenceNumber);
        var terminal = Assert.IsAssignableFrom<IStreamingResponseEventWithResponse>(suppliedEvent);
        Assert.Same(terminal.Response, await service.GetResponseAsync(initialResponse.Id, timeout.Token));
    }

    private static async Task<List<StreamingResponseEvent>> ReadEventsAsync(
        IAsyncEnumerable<StreamingResponseEvent> events, CancellationToken cancellationToken)
    {
        List<StreamingResponseEvent> result = [];
        await foreach (StreamingResponseEvent item in events.WithCancellation(cancellationToken))
        {
            result.Add(item);
        }

        return result;
    }

    private sealed class ControlledResponseExecutor(
        Func<AgentInvocationContext, CreateResponse, IReadOnlyList<StreamingResponseEvent>>? initialEventsFactory = null) : IResponseExecutor,
        IAsyncEnumerable<StreamingResponseEvent>, IAsyncEnumerator<StreamingResponseEvent>, IValueTaskSource<bool>
    {
        private ManualResetValueTaskSourceCore<bool> _completion = new() { RunContinuationsAsynchronously = false };
        private int _continuationThreadId;
        private int _disposalThreadId;
        private IReadOnlyList<StreamingResponseEvent> _events = [];
        private int _nextEvent;

        public TaskCompletionSource ContinuationRegistered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public int ContinuationThreadId => Volatile.Read(ref this._continuationThreadId);

        public int DisposalThreadId => Volatile.Read(ref this._disposalThreadId);

        public StreamingResponseEvent Current { get; private set; } = null!;

        public string ResponseId { get; private set; } = string.Empty;

        public CancellationToken ExecutionCancellationToken { get; private set; }

        public ValueTask<ResponseError?> ValidateRequestAsync(CreateResponse request, CancellationToken cancellationToken = default)
            => ValueTask.FromResult<ResponseError?>(null);

        public IAsyncEnumerable<StreamingResponseEvent> ExecuteAsync(
            AgentInvocationContext context,
            CreateResponse request,
            IReadOnlyList<ChatMessage>? conversationHistory = null,
            CancellationToken cancellationToken = default)
        {
            this._events = initialEventsFactory?.Invoke(context, request) ?? [];
            this.ResponseId = context.ResponseId;
            this.ExecutionCancellationToken = cancellationToken;
            return this;
        }

        public IAsyncEnumerator<StreamingResponseEvent> GetAsyncEnumerator(CancellationToken cancellationToken = default) => this;

        public ValueTask<bool> MoveNextAsync()
        {
            if (this._nextEvent < this._events.Count)
            {
                this.Current = this._events[this._nextEvent++];
                return ValueTask.FromResult(true);
            }

            return new(this, this._completion.Version);
        }

        public ValueTask DisposeAsync()
        {
            Volatile.Write(ref this._disposalThreadId, Environment.CurrentManagedThreadId);
            return default;
        }

        public void Complete(string outcome)
        {
            if (outcome == "failed")
            {
                this._completion.SetException(new InvalidOperationException("Test executor failure."));
            }
            else if (outcome == "cancelled")
            {
                this._completion.SetException(new OperationCanceledException());
            }
            else
            {
                this._completion.SetResult(false);
            }
        }

        public bool GetResult(short token)
        {
            Volatile.Write(ref this._continuationThreadId, Environment.CurrentManagedThreadId);
            return this._completion.GetResult(token);
        }

        public ValueTaskSourceStatus GetStatus(short token) => this._completion.GetStatus(token);

        public void OnCompleted(Action<object?> continuation, object? state, short token, ValueTaskSourceOnCompletedFlags flags)
        {
            this._completion.OnCompleted(continuation, state, token, flags);
            this.ContinuationRegistered.SetResult();
        }
    }
}
