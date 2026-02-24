// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Default implementation of <see cref="IMcpToolHandler"/> using the MCP C# SDK.
/// </summary>
/// <remarks>
/// This provider supports per-server authentication via the <c>httpClientProvider</c> callback.
/// The callback allows different MCP servers to use different authentication configurations by returning
/// a pre-configured <see cref="HttpClient"/> for each server.
/// </remarks>
public sealed class DefaultMcpToolHandler : IMcpToolHandler, IAsyncDisposable
{
    private readonly Func<string, CancellationToken, Task<HttpClient?>>? _httpClientProvider;
    private readonly Dictionary<string, McpClient> _clients = [];
    private readonly Dictionary<string, HttpClient> _ownedHttpClients = [];
    private readonly SemaphoreSlim _clientLock = new(1, 1);

    /// <summary>
    /// Initializes a new instance of the <see cref="DefaultMcpToolHandler"/> class.
    /// </summary>
    /// <param name="httpClientProvider">
    /// An optional callback that provides an <see cref="HttpClient"/> for each MCP server.
    /// The callback receives (serverUrl, cancellationToken) and should return an HttpClient
    /// configured with any required authentication. Return <see langword="null"/> to use a default HttpClient with no auth.
    /// </param>
    public DefaultMcpToolHandler(Func<string, CancellationToken, Task<HttpClient?>>? httpClientProvider = null)
    {
        this._httpClientProvider = httpClientProvider;
    }

    /// <inheritdoc/>
    public async Task<McpServerToolResultContent> InvokeToolAsync(
        string serverUrl,
        string? serverLabel,
        string toolName,
        IDictionary<string, object?>? arguments,
        IDictionary<string, string>? headers,
        string? connectionName,
        CancellationToken cancellationToken = default)
    {
        //TODO: Handle connectionName and server label appropriately when Hosted scenario supports them. For now, ignore
        McpServerToolResultContent resultContent = new("McpServerToolcallId");
        McpClient client = await this.GetOrCreateClientAsync(serverUrl, serverLabel, headers, cancellationToken).ConfigureAwait(false);

        // Convert IDictionary to IReadOnlyDictionary for CallToolAsync
        IReadOnlyDictionary<string, object?>? readOnlyArguments = arguments is null
            ? null
            : arguments as IReadOnlyDictionary<string, object?> ?? new Dictionary<string, object?>(arguments);

        CallToolResult result = await client.CallToolAsync(
            toolName,
            readOnlyArguments,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        // Map MCP content blocks to MEAI AIContent types
        PopulateResultContent(resultContent, result);

        return resultContent;
    }

    /// <inheritdoc/>
    public async ValueTask DisposeAsync()
    {
        await this._clientLock.WaitAsync().ConfigureAwait(false);
        try
        {
            foreach (McpClient client in this._clients.Values)
            {
                await client.DisposeAsync().ConfigureAwait(false);
            }

            this._clients.Clear();

            // Dispose only HttpClients that the handler created (not user-provided ones)
            foreach (HttpClient httpClient in this._ownedHttpClients.Values)
            {
                httpClient.Dispose();
            }

            this._ownedHttpClients.Clear();
        }
        finally
        {
            this._clientLock.Release();
        }

        this._clientLock.Dispose();
    }

    private async Task<McpClient> GetOrCreateClientAsync(
        string serverUrl,
        string? serverLabel,
        IDictionary<string, string>? headers,
        CancellationToken cancellationToken)
    {
        string cacheKey = $"{serverUrl.Trim().ToUpperInvariant()}";

        await this._clientLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (this._clients.TryGetValue(cacheKey, out McpClient? existingClient))
            {
                return existingClient;
            }

            McpClient newClient = await this.CreateClientAsync(serverUrl, serverLabel, headers, cacheKey, cancellationToken).ConfigureAwait(false);
            this._clients[cacheKey] = newClient;
            return newClient;
        }
        finally
        {
            this._clientLock.Release();
        }
    }

    private async Task<McpClient> CreateClientAsync(
        string serverUrl,
        string? serverLabel,
        IDictionary<string, string>? headers,
        string cacheKey,
        CancellationToken cancellationToken)
    {
        // Get HttpClient from provider or create a default one
        HttpClient? httpClient = null;

        if (this._httpClientProvider is not null)
        {
            httpClient = await this._httpClientProvider(serverUrl, cancellationToken).ConfigureAwait(false);
        }

        if (httpClient is null)
        {
            httpClient = new HttpClient();
            this._ownedHttpClients[cacheKey] = httpClient;
        }

        HttpClientTransportOptions transportOptions = new()
        {
            Endpoint = new Uri(serverUrl),
            Name = serverLabel ?? "McpClient",
            AdditionalHeaders = headers,
            TransportMode = HttpTransportMode.AutoDetect
        };

        HttpClientTransport transport = new(transportOptions, httpClient);

        return await McpClient.CreateAsync(transport, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    private static void PopulateResultContent(McpServerToolResultContent resultContent, CallToolResult result)
    {
        // Ensure Output list is initialized
        resultContent.Output ??= [];

        if (result.IsError == true)
        {
            // Collect error text from content blocks
            string? errorText = null;
            if (result.Content is not null)
            {
                foreach (ContentBlock block in result.Content)
                {
                    if (block is TextContentBlock textBlock)
                    {
                        errorText = errorText is null ? textBlock.Text : $"{errorText}\n{textBlock.Text}";
                    }
                }
            }

            resultContent.Output.Add(new TextContent($"Error: {errorText ?? "Unknown error from MCP Server call"}"));
            return;
        }

        if (result.Content is null || result.Content.Count == 0)
        {
            return;
        }

        // Map each MCP content block to an MEAI AIContent type
        foreach (ContentBlock block in result.Content)
        {
            AIContent content = ConvertContentBlock(block);
            if (content is not null)
            {
                resultContent.Output.Add(content);
            }
        }
    }

    private static AIContent ConvertContentBlock(ContentBlock block)
    {
        return block switch
        {
            TextContentBlock text => new TextContent(text.Text),
            ImageContentBlock image => CreateDataContentFromBase64(image.Data, image.MimeType ?? "image/*"),
            AudioContentBlock audio => CreateDataContentFromBase64(audio.Data, audio.MimeType ?? "audio/*"),
            _ => new TextContent(block.ToString() ?? string.Empty),
        };
    }

    private static DataContent CreateDataContentFromBase64(string? base64Data, string mediaType)
    {
        if (string.IsNullOrEmpty(base64Data))
        {
            return new DataContent($"data:{mediaType};base64,", mediaType);
        }

        // If it's already a data URI, use it directly
        if (base64Data.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
        {
            return new DataContent(base64Data, mediaType);
        }

        // Otherwise, construct a data URI from the base64 data
        return new DataContent($"data:{mediaType};base64,{base64Data}", mediaType);
    }
}
