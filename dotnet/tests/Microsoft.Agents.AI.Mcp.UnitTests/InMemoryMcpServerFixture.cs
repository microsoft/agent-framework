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

    public McpClient Client { get; }

    public int CreatedTaskCount => this._taskStore?.CreatedTaskCount ?? 0;

    public int InputRequestCount => this._taskStore?.InputRequestCount ?? 0;

    public int PollCount => this._taskStore?.PollCount ?? 0;

    public int RemoteCancellationCount => this._taskStore?.RemoteCancellationCount ?? 0;

    public Task TaskCreated => this._taskStore?.TaskCreated
        ?? throw new InvalidOperationException("Tasks are not enabled for this fixture.");

    public Task FirstPollObserved => this._taskStore?.FirstPollObserved
        ?? throw new InvalidOperationException("Tasks are not enabled for this fixture.");

    public Task RemoteCancellationObserved => this._taskStore?.RemoteCancellationObserved
        ?? throw new InvalidOperationException("Tasks are not enabled for this fixture.");

    private InMemoryMcpServerFixture(
        ServiceProvider serviceProvider,
        McpClient client,
        Task serverLoop,
        CancellationTokenSource cts,
        RecordingMcpTaskStore? taskStore)
    {
        this._serviceProvider = serviceProvider;
        this.Client = client;
        this._serverLoop = serverLoop;
        this._cts = cts;
        this._taskStore = taskStore;
    }

    public static async Task<InMemoryMcpServerFixture> CreateAsync(
        McpServerPrimitiveCollection<McpServerTool> tools,
        bool enableTasks = true,
        McpClientOptions? clientOptions = null,
        bool ignoreInputResponses = false,
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
        IMcpServerBuilder builder = services
            .AddMcpServer(options => options.ServerInfo = new Implementation { Name = "test-server", Version = "1.0.0" })
            .WithStreamServerTransport(serverReadStream, serverWriteStream)
            .WithTools(tools);

        RecordingMcpTaskStore? taskStore = null;
        if (enableTasks)
        {
            taskStore = new RecordingMcpTaskStore(ignoreInputResponses);
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

        return new InMemoryMcpServerFixture(serviceProvider, client, serverLoop, cts, taskStore);
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

    private sealed class RecordingMcpTaskStore : IMcpTaskStore
    {
        private readonly InMemoryMcpTaskStore _inner = new() { DefaultPollIntervalMs = 10 };
        private readonly bool _ignoreInputResponses;
        private readonly TaskCompletionSource<object?> _taskCreated =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource<object?> _firstPollObserved =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource<object?> _remoteCancellationObserved =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _createdTaskCount;
        private int _inputRequestCount;
        private int _pollCount;
        private int _remoteCancellationCount;
        private string? _latestTaskId;

        public RecordingMcpTaskStore(bool ignoreInputResponses)
        {
            this._ignoreInputResponses = ignoreInputResponses;
        }

        public int CreatedTaskCount => this._createdTaskCount;

        public int InputRequestCount => this._inputRequestCount;

        public int PollCount => this._pollCount;

        public int RemoteCancellationCount => this._remoteCancellationCount;

        public Task TaskCreated => this._taskCreated.Task;

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
            this._latestTaskId = task.TaskId;
            _ = Interlocked.Increment(ref this._createdTaskCount);
            _ = this._taskCreated.TrySetResult(null);
            return task;
        }

        public Task<McpTaskInfo?> GetTaskAsync(string taskId, CancellationToken cancellationToken = default)
        {
            _ = Interlocked.Increment(ref this._pollCount);
            _ = this._firstPollObserved.TrySetResult(null);
            return this._inner.GetTaskAsync(taskId, cancellationToken);
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
                _ = Interlocked.Increment(ref this._remoteCancellationCount);
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
            CancellationToken cancellationToken = default) =>
            this._ignoreInputResponses
                ? Task.CompletedTask
                : this._inner.ResolveInputRequestsAsync(taskId, inputResponses, cancellationToken);

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
    }
}
