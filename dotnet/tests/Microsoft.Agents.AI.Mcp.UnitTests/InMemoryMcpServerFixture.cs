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
            taskStore = new RecordingMcpTaskStore();
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

    private sealed class RecordingMcpTaskStore : IMcpTaskStore
    {
        private readonly InMemoryMcpTaskStore _inner = new() { DefaultPollIntervalMs = 10 };
        private int _createdTaskCount;
        private int _inputRequestCount;

        public int CreatedTaskCount => this._createdTaskCount;

        public int InputRequestCount => this._inputRequestCount;

        public event Action<InputResponseReceivedEventArgs>? InputResponseReceived
        {
            add => this._inner.InputResponseReceived += value;
            remove => this._inner.InputResponseReceived -= value;
        }

        public async Task<McpTaskInfo> CreateTaskAsync(CancellationToken cancellationToken = default)
        {
            McpTaskInfo task = await this._inner.CreateTaskAsync(cancellationToken).ConfigureAwait(false);
            _ = Interlocked.Increment(ref this._createdTaskCount);
            return task;
        }

        public Task<McpTaskInfo?> GetTaskAsync(string taskId, CancellationToken cancellationToken = default) =>
            this._inner.GetTaskAsync(taskId, cancellationToken);

        public Task SetCompletedAsync(string taskId, JsonElement result, CancellationToken cancellationToken = default) =>
            this._inner.SetCompletedAsync(taskId, result, cancellationToken);

        public Task SetFailedAsync(string taskId, JsonElement error, CancellationToken cancellationToken = default) =>
            this._inner.SetFailedAsync(taskId, error, cancellationToken);

        public Task<bool> SetCancelledAsync(string taskId, CancellationToken cancellationToken = default) =>
            this._inner.SetCancelledAsync(taskId, cancellationToken);

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
            this._inner.ResolveInputRequestsAsync(taskId, inputResponses, cancellationToken);
    }
}
