// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.IO.Pipelines;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging.Abstractions;
using ModelContextProtocol;
using ModelContextProtocol.Client;
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
    private readonly McpServer _server;
    private readonly Task _serverLoop;
    private readonly CancellationTokenSource _cts;

    public McpClient Client { get; }

    private InMemoryMcpServerFixture(McpServer server, McpClient client, Task serverLoop, CancellationTokenSource cts)
    {
        this._server = server;
        this.Client = client;
        this._serverLoop = serverLoop;
        this._cts = cts;
    }

    public static async Task<InMemoryMcpServerFixture> CreateAsync(
        McpServerPrimitiveCollection<McpServerTool> tools,
        CancellationToken cancellationToken = default)
    {
        Pipe clientToServer = new();
        Pipe serverToClient = new();

        // Stream conventions:
        //   StreamClientTransport(serverInput, serverOutput, ...): serverInput is what the client
        //   WRITES to (server reads it); serverOutput is what the client READS from (server writes it).
        //   StreamServerTransport(input, output, ...): input is what the server READS from; output
        //   is what the server WRITES to.
        Stream clientWriteStream = clientToServer.Writer.AsStream();
        Stream clientReadStream = serverToClient.Reader.AsStream();
        Stream serverReadStream = clientToServer.Reader.AsStream();
        Stream serverWriteStream = serverToClient.Writer.AsStream();

        StreamServerTransport serverTransport = new(
            serverReadStream,
            serverWriteStream,
            "test-server",
            NullLoggerFactory.Instance);

        McpServerOptions serverOptions = new()
        {
            ServerInfo = new Implementation { Name = "test-server", Version = "1.0.0" },
            TaskStore = new InMemoryMcpTaskStore(),
            ToolCollection = tools,
        };

        McpServer server = McpServer.Create(
            serverTransport,
            serverOptions,
            NullLoggerFactory.Instance,
            EmptyServiceProvider.Instance);

        CancellationTokenSource cts = new();
        Task serverLoop = Task.Run(() => server.RunAsync(cts.Token), cts.Token);

        StreamClientTransport clientTransport = new(
            clientWriteStream,
            clientReadStream,
            NullLoggerFactory.Instance);

        McpClient client = await McpClient.CreateAsync(
            clientTransport,
            clientOptions: null,
            NullLoggerFactory.Instance,
            cancellationToken).ConfigureAwait(false);

        return new InMemoryMcpServerFixture(server, client, serverLoop, cts);
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

        try
        {
            await this._server.DisposeAsync().ConfigureAwait(false);
        }
        catch
        {
            // Best effort.
        }

        this._cts.Dispose();
    }
}
