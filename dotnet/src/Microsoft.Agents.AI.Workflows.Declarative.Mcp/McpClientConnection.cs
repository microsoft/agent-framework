// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Threading.Tasks;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI.Workflows.Declarative.Mcp;

/// <summary>
/// Owns an MCP session, its transport, and any lease on a pooled HTTP client.
/// </summary>
internal sealed class McpClientConnection(
    McpClient client,
    IAsyncDisposable transport,
    IAsyncDisposable? ownedHttpClientLease = null) : IAsyncDisposable
{
    public McpClient Client { get; } = client;

    public async ValueTask DisposeAsync()
    {
        try
        {
            await DisposeResourceAsync(this.Client, "session").ConfigureAwait(false);
        }
        finally
        {
            try
            {
                // McpClient owns the connected session, not the reusable transport factory.
                await DisposeResourceAsync(transport, "transport").ConfigureAwait(false);
            }
            finally
            {
                if (ownedHttpClientLease is not null)
                {
                    await ownedHttpClientLease.DisposeAsync().ConfigureAwait(false);
                }
            }
        }
    }

    internal static async ValueTask DisposeResourceAsync<T>(T resource, string resourceName)
        where T : IAsyncDisposable
    {
        try
        {
            await resource.DisposeAsync().ConfigureAwait(false);
        }
        catch (Exception exception) when (exception is not OperationCanceledException)
        {
            Trace.TraceWarning("Failed to dispose MCP {0}: {1}", resourceName, exception);
        }
    }
}
