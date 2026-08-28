// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Pipelines;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Client;
using ModelContextProtocol.Extensions.Tasks;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;

namespace Microsoft.Agents.AI.Mcp.UnitTests;

/// <summary>
/// In-process MCP server fixture that pairs a <see cref="McpServer"/> and a <see cref="McpClient"/>
/// over duplex <see cref="Pipe"/>-backed streams so unit tests can exercise the
/// real task-augmentation protocol without spawning a child process or opening a socket.
/// </summary>
internal sealed class InMemoryMcpServerFixture : IAsyncDisposable
{
    private readonly ServiceProvider _serviceProvider;
    private readonly Task _serverLoop;
    private readonly CancellationTokenSource _cts;
    private readonly RecordingMcpTaskStore? _taskStore;
    private readonly TaskRequestObserver _taskRequestObserver;

    public McpClient Client { get; }

    public int CreatedTaskCount => this._taskStore?.CreatedTaskCount ?? 0;

    public int InputRequestCount => this._taskStore?.InputRequestCount ?? 0;

    public int PollCount => this._taskStore?.PollCount ?? 0;

    public int SuccessfulCancellationTransitionCount =>
        this._taskStore?.SuccessfulCancellationTransitionCount ?? 0;

    public int CancellationRequestCount => this._taskRequestObserver.CancellationRequestCount;

    public Task FirstPollObserved => this._taskStore?.FirstPollObserved
        ?? throw new InvalidOperationException("Tasks are not enabled for this fixture.");

    public Task RemoteCancellationObserved => this._taskStore?.RemoteCancellationObserved
        ?? throw new InvalidOperationException("Tasks are not enabled for this fixture.");

    private InMemoryMcpServerFixture(
        ServiceProvider serviceProvider,
        McpClient client,
        Task serverLoop,
        CancellationTokenSource cts,
        RecordingMcpTaskStore? taskStore,
        TaskRequestObserver taskRequestObserver)
    {
        this._serviceProvider = serviceProvider;
        this.Client = client;
        this._serverLoop = serverLoop;
        this._cts = cts;
        this._taskStore = taskStore;
        this._taskRequestObserver = taskRequestObserver;
    }

    public static async Task<InMemoryMcpServerFixture> CreateAsync(
        McpServerPrimitiveCollection<McpServerTool> tools,
        bool enableTasks = true,
        McpClientOptions? clientOptions = null,
        bool ignoreInputResponses = false,
        long initialPollIntervalMs = 10,
        long? updatedPollIntervalMs = null,
        bool omitPollIntervals = false,
        Exception? getTaskException = null,
        Exception? resolveInputRequestsException = null,
        CancellationToken cancellationToken = default)
    {
        Pipe clientToServer = new();
        Pipe serverToClient = new();

        Stream clientWriteStream = clientToServer.Writer.AsStream();
        Stream clientReadStream = serverToClient.Reader.AsStream();
        Stream serverReadStream = clientToServer.Reader.AsStream();
        Stream serverWriteStream = serverToClient.Writer.AsStream();

        var services = new ServiceCollection();
        services.AddLogging(builder => builder.ClearProviders());
        var taskRequestObserver = new TaskRequestObserver();
        IMcpServerBuilder builder = services
            .AddMcpServer(options =>
            {
                options.ServerInfo = new Implementation { Name = "test-server", Version = "1.0.0" };
                options.Filters.Message.IncomingFilters.Add(next => async (context, ct) =>
                {
                    taskRequestObserver.Observe(context.JsonRpcMessage);
                    await next(context, ct).ConfigureAwait(false);
                });
            })
            .WithStreamServerTransport(serverReadStream, serverWriteStream)
            .WithTools(tools);

        RecordingMcpTaskStore? taskStore = null;
        if (enableTasks)
        {
            taskStore = new RecordingMcpTaskStore(
                ignoreInputResponses,
                initialPollIntervalMs,
                updatedPollIntervalMs,
                omitPollIntervals,
                getTaskException,
                resolveInputRequestsException);
            builder.WithTasks(taskStore);
        }

        ServiceProvider serviceProvider = services.BuildServiceProvider();
        McpServer server = serviceProvider.GetRequiredService<McpServer>();
        CancellationTokenSource cts = new();
        Task serverLoop = server.RunAsync(cts.Token);

        StreamClientTransport clientTransport = new(
            clientWriteStream,
            clientReadStream);

        McpClient client = await McpClient.CreateAsync(
            clientTransport,
            clientOptions,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        return new InMemoryMcpServerFixture(
            serviceProvider,
            client,
            serverLoop,
            cts,
            taskStore,
            taskRequestObserver);
    }

    public async ValueTask DisposeAsync()
    {
        try
        {
            await this.Client.DisposeAsync().ConfigureAwait(false);
        }
        catch
        {
            // Best effort.
        }

        this._cts.Cancel();

        try
        {
            await this._serverLoop.ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            // Expected.
        }
        catch
        {
            // Best effort.
        }

        await this._serviceProvider.DisposeAsync().ConfigureAwait(false);
        this._cts.Dispose();
    }

    public Task CancelLatestTaskAsync(CancellationToken cancellationToken = default) =>
        this._taskStore?.CancelLatestTaskAsync(cancellationToken)
        ?? throw new InvalidOperationException("Tasks are not enabled for this fixture.");

    public Task FailLatestTaskAsync(JsonElement error, CancellationToken cancellationToken = default) =>
        this._taskStore?.FailLatestTaskAsync(error, cancellationToken)
        ?? throw new InvalidOperationException("Tasks are not enabled for this fixture.");

    public Task CompleteLatestTaskAsync(JsonElement result, CancellationToken cancellationToken = default) =>
        this._taskStore?.CompleteLatestTaskAsync(result, cancellationToken)
        ?? throw new InvalidOperationException("Tasks are not enabled for this fixture.");

    private sealed class TaskRequestObserver
    {
        private int _cancellationRequestCount;

        public int CancellationRequestCount => this._cancellationRequestCount;

        public void Observe(JsonRpcMessage message)
        {
            if (message is JsonRpcRequest { Method: TasksProtocol.MethodTasksCancel })
            {
                _ = Interlocked.Increment(ref this._cancellationRequestCount);
            }
        }
    }

    private sealed class RecordingMcpTaskStore : IMcpTaskStore
    {
        private readonly InMemoryMcpTaskStore _inner;
        private readonly bool _ignoreInputResponses;
        private readonly long? _updatedPollIntervalMs;
        private readonly bool _omitPollIntervals;
        private readonly Exception? _getTaskException;
        private readonly Exception? _resolveInputRequestsException;
        private readonly TaskCompletionSource<object?> _firstPollObserved =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource<object?> _remoteCancellationObserved =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _createdTaskCount;
        private int _inputRequestCount;
        private int _pollCount;
        private int _successfulCancellationTransitionCount;
        private string? _latestTaskId;

        public RecordingMcpTaskStore(
            bool ignoreInputResponses,
            long initialPollIntervalMs,
            long? updatedPollIntervalMs,
            bool omitPollIntervals,
            Exception? getTaskException,
            Exception? resolveInputRequestsException)
        {
            this._ignoreInputResponses = ignoreInputResponses;
            this._updatedPollIntervalMs = updatedPollIntervalMs;
            this._omitPollIntervals = omitPollIntervals;
            this._getTaskException = getTaskException;
            this._resolveInputRequestsException = resolveInputRequestsException;
            this._inner = new InMemoryMcpTaskStore { DefaultPollIntervalMs = initialPollIntervalMs };
        }

        public int CreatedTaskCount => this._createdTaskCount;

        public int InputRequestCount => this._inputRequestCount;

        public int PollCount => this._pollCount;

        public int SuccessfulCancellationTransitionCount =>
            this._successfulCancellationTransitionCount;

        public Task FirstPollObserved => this._firstPollObserved.Task;

        public Task RemoteCancellationObserved => this._remoteCancellationObserved.Task;

        public event Action<InputResponseReceivedEventArgs>? InputResponseReceived
        {
            add => this._inner.InputResponseReceived += value;
            remove => this._inner.InputResponseReceived -= value;
        }

        public async Task<McpTaskInfo> CreateTaskAsync(CancellationToken cancellationToken = default)
        {
            McpTaskInfo task = await this._inner.CreateTaskAsync(cancellationToken).ConfigureAwait(false);
            if (this._omitPollIntervals)
            {
                task = task with { PollIntervalMs = null };
            }

            this._latestTaskId = task.TaskId;
            _ = Interlocked.Increment(ref this._createdTaskCount);
            return task;
        }

        public async Task<McpTaskInfo?> GetTaskAsync(string taskId, CancellationToken cancellationToken = default)
        {
            _ = Interlocked.Increment(ref this._pollCount);
            _ = this._firstPollObserved.TrySetResult(null);
            if (this._getTaskException is not null)
            {
                throw this._getTaskException;
            }

            McpTaskInfo? task = await this._inner.GetTaskAsync(taskId, cancellationToken).ConfigureAwait(false);
            if (task is not null && this._omitPollIntervals)
            {
                task = task with { PollIntervalMs = null };
            }
            else if (task is not null && this._updatedPollIntervalMs is { } updatedPollIntervalMs)
            {
                task = task with { PollIntervalMs = updatedPollIntervalMs };
            }

            return task;
        }

        public Task SetCompletedAsync(string taskId, JsonElement result, CancellationToken cancellationToken = default) =>
            this._inner.SetCompletedAsync(taskId, result, cancellationToken);

        public Task SetFailedAsync(string taskId, JsonElement error, CancellationToken cancellationToken = default) =>
            this._inner.SetFailedAsync(taskId, error, cancellationToken);

        public async Task<bool> SetCancelledAsync(string taskId, CancellationToken cancellationToken = default)
        {
            bool result = await this._inner.SetCancelledAsync(taskId, cancellationToken).ConfigureAwait(false);
            // Count only the first successful terminal transition. The SDK background runner
            // may make a later idempotent cancellation attempt after cleanup has already won.
            if (result)
            {
                _ = Interlocked.Increment(ref this._successfulCancellationTransitionCount);
                _ = this._remoteCancellationObserved.TrySetResult(null);
            }

            return result;
        }

        public Task SetInputRequestsAsync(
            string taskId,
            IDictionary<string, InputRequest> inputRequests,
            CancellationToken cancellationToken = default)
        {
            _ = Interlocked.Add(ref this._inputRequestCount, inputRequests.Count);
            return this._inner.SetInputRequestsAsync(taskId, inputRequests, cancellationToken);
        }

        public Task ResolveInputRequestsAsync(
            string taskId,
            IDictionary<string, InputResponse> inputResponses,
            CancellationToken cancellationToken = default)
        {
            if (this._resolveInputRequestsException is not null)
            {
                throw this._resolveInputRequestsException;
            }

            return this._ignoreInputResponses
                ? Task.CompletedTask
                : this._inner.ResolveInputRequestsAsync(taskId, inputResponses, cancellationToken);
        }

        public async Task CancelLatestTaskAsync(CancellationToken cancellationToken)
        {
            string taskId = this._latestTaskId
                ?? throw new InvalidOperationException("No task has been created.");
            _ = await this.SetCancelledAsync(taskId, cancellationToken).ConfigureAwait(false);
        }

        public Task FailLatestTaskAsync(JsonElement error, CancellationToken cancellationToken)
        {
            string taskId = this._latestTaskId
                ?? throw new InvalidOperationException("No task has been created.");
            return this.SetFailedAsync(taskId, error, cancellationToken);
        }

        public Task CompleteLatestTaskAsync(JsonElement result, CancellationToken cancellationToken)
        {
            string taskId = this._latestTaskId
                ?? throw new InvalidOperationException("No task has been created.");
            return this.SetCompletedAsync(taskId, result, cancellationToken);
        }
    }
}
