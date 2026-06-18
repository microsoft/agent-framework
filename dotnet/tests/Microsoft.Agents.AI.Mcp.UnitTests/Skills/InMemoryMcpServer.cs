// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics.CodeAnalysis;
using System.IO.Pipelines;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;

namespace Microsoft.Agents.AI.Skills.Mcp.UnitTests;

/// <summary>
/// Spins up an in-memory MCP server hosting a configurable set of resources, and returns an
/// <see cref="McpClient"/> connected to it. Disposes both ends together.
/// </summary>
[SuppressMessage("Performance", "CA1812:Avoid uninstantiated internal classes", Justification = "Instantiated by AgentMcpSkillsSourceTests which is temporarily excluded from compilation.")]
internal sealed class InMemoryMcpServer : IAsyncDisposable
{
    private readonly Pipe _clientToServerPipe = new();
    private readonly Pipe _serverToClientPipe = new();
    private readonly CancellationTokenSource _cts = new();
    private readonly ServiceProvider _serviceProvider;
    private readonly Task _serverTask;

    public InMemoryMcpServer(Action<IMcpServerBuilder> configure)
    {
        var services = new ServiceCollection();
        services.AddLogging(builder => builder.AddProvider(NullLoggerProvider.Instance));

        IMcpServerBuilder builder = services
            .AddMcpServer()
            .WithStreamServerTransport(
                inputStream: this._clientToServerPipe.Reader.AsStream(),
                outputStream: this._serverToClientPipe.Writer.AsStream());

        configure(builder);

        this._serviceProvider = services.BuildServiceProvider();
        var server = this._serviceProvider.GetRequiredService<McpServer>();
        this._serverTask = server.RunAsync(this._cts.Token);
    }

    public async Task<McpClient> CreateClientAsync(CancellationToken cancellationToken = default)
    {
        return await McpClient.CreateAsync(
            new StreamClientTransport(
                serverInput: this._clientToServerPipe.Writer.AsStream(),
                serverOutput: this._serverToClientPipe.Reader.AsStream()),
            cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    public async ValueTask DisposeAsync()
    {
        await this._cts.CancelAsync().ConfigureAwait(false);

        this._clientToServerPipe.Writer.Complete();
        this._serverToClientPipe.Writer.Complete();

        try
        {
            await this._serverTask.ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            // Expected when the server is cancelled during shutdown.
        }

        await this._serviceProvider.DisposeAsync().ConfigureAwait(false);
        this._cts.Dispose();
    }
}
