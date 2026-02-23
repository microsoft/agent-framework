// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Extensions.AI;
using ModelContextProtocol.Authentication;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Default implementation of <see cref="IMcpToolHandler"/> using the MCP C# SDK.
/// </summary>
/// <remarks>
/// <para>
/// This provider supports multiple authentication strategies:
/// </para>
/// <list type="bullet">
/// <item>
/// <description>
/// <b>TokenCredential (silent auth)</b>: Uses Azure.Core <see cref="TokenCredential"/> to acquire tokens silently.
/// This is the preferred method for Azure Managed Identity, Service Principal, or any Azure AD-based auth.
/// </description>
/// </item>
/// <item>
/// <description>
/// <b>AuthorizationRedirectDelegate (interactive auth)</b>: Falls back to OAuth redirect flow if silent auth fails
/// or if <see cref="TokenCredential"/> is not provided.
/// </description>
/// </item>
/// <item>
/// <description>
/// <b>Pre-configured HttpClient</b>: If the supplied <see cref="HttpClient"/> has authentication already configured
/// (e.g., via a <see cref="DelegatingHandler"/>), it will be used directly for MCP server calls.
/// </description>
/// </item>
/// </list>
/// </remarks>
public sealed class DefaultMcpToolHandler : IMcpToolHandler, IAsyncDisposable
{
    private readonly TokenCredential? _tokenCredential;
    private readonly string[]? _tokenScopes;
    private readonly AuthorizationRedirectDelegate? _authorizationHandler;
    private readonly HttpClient? _httpClient;
    private readonly bool _disposeHttpClient;
    private readonly bool _httpClientHasAuth;
    private readonly Dictionary<string, McpClient> _clients = [];
    private readonly SemaphoreSlim _clientLock = new(1, 1);

    /// <summary>
    /// Initializes a new instance of the <see cref="DefaultMcpToolHandler"/> class.
    /// </summary>
    /// <param name="tokenCredential">
    /// An optional <see cref="TokenCredential"/> for silent token acquisition (e.g., DefaultAzureCredential, ManagedIdentityCredential).
    /// If provided, tokens will be acquired silently before falling back to the redirect handler.
    /// </param>
    /// <param name="tokenScopes">
    /// The scopes to request when acquiring tokens. Required if <paramref name="tokenCredential"/> is provided.
    /// For example: <c>new[] { "https://api.example.com/.default" }</c>
    /// </param>
    /// <param name="authorizationHandler">
    /// An optional delegate to handle OAuth authorization redirect flows. Used as a fallback if silent auth fails.
    /// Use the MCP SDK's <see cref="AuthorizationRedirectDelegate"/> type.
    /// </param>
    /// <param name="httpClient">
    /// An optional HTTP client to use for connections. If not provided, a default client will be created.
    /// </param>
    /// <param name="httpClientHasAuth">
    /// Set to <c>true</c> if the supplied <paramref name="httpClient"/> already has authentication configured
    /// (e.g., via a <see cref="DelegatingHandler"/> that adds Authorization headers). When <c>true</c>, the provider
    /// will not configure any additional authentication and will rely on the client's existing auth setup.
    /// </param>
    public DefaultMcpToolHandler(
        TokenCredential? tokenCredential = null,
        string[]? tokenScopes = null,
        AuthorizationRedirectDelegate? authorizationHandler = null,
        HttpClient? httpClient = null,
        bool httpClientHasAuth = false)
    {
        this._tokenCredential = tokenCredential;
        this._tokenScopes = tokenScopes;
        this._authorizationHandler = authorizationHandler;
        this._httpClientHasAuth = httpClientHasAuth;

        if (httpClient is not null)
        {
            this._httpClient = httpClient;
            this._disposeHttpClient = false;
        }
        else
        {
            this._httpClient = new HttpClient();
            this._disposeHttpClient = true;
        }
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
        McpServerToolResultContent resultContent = new("McpServerToolcallId");
        McpClient client = await this.GetOrCreateClientAsync(serverUrl, serverLabel, headers, connectionName, cancellationToken).ConfigureAwait(false);

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
        }
        finally
        {
            this._clientLock.Release();
        }

        if (this._disposeHttpClient)
        {
            this._httpClient?.Dispose();
        }

        this._clientLock.Dispose();
    }

    private async Task<McpClient> GetOrCreateClientAsync(
        string serverUrl,
        string? serverLabel,
        IDictionary<string, string>? headers,
        string? connectionName,
        CancellationToken cancellationToken)
    {
        string cacheKey = $"{serverUrl}|{serverLabel}|{connectionName}";

        await this._clientLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (this._clients.TryGetValue(cacheKey, out McpClient? existingClient))
            {
                return existingClient;
            }

            McpClient newClient = await this.CreateClientAsync(serverUrl, serverLabel, headers, cancellationToken).ConfigureAwait(false);
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
        CancellationToken cancellationToken)
    {
        // Merge headers with token if using TokenCredential
        IDictionary<string, string>? effectiveHeaders = headers;
        if (this._tokenCredential is not null && this._tokenScopes is not null && !this._httpClientHasAuth)
        {
            effectiveHeaders = await this.AddTokenToHeadersAsync(headers, cancellationToken).ConfigureAwait(false);
        }

        HttpClientTransportOptions transportOptions = new()
        {
            Endpoint = new Uri(serverUrl),
            Name = serverLabel ?? "McpClient",
            AdditionalHeaders = effectiveHeaders,
            TransportMode = HttpTransportMode.AutoDetect
        };

        // Configure OAuth redirect handler if provided and not using pre-configured HttpClient auth
        if (this._authorizationHandler is not null && !this._httpClientHasAuth)
        {
            transportOptions.OAuth = new()
            {
                DynamicClientRegistration = new()
                {
                    ClientName = serverLabel ?? "WorkflowMcpClient",
                },
                RedirectUri = new Uri("http://localhost:0/callback"),
                AuthorizationRedirectDelegate = this._authorizationHandler,
            };
        }

        HttpClientTransport transport = new(transportOptions, this._httpClient!);

        return await McpClient.CreateAsync(transport, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    private async Task<IDictionary<string, string>?> AddTokenToHeadersAsync(
        IDictionary<string, string>? existingHeaders,
        CancellationToken cancellationToken)
    {
        if (this._tokenCredential is null || this._tokenScopes is null)
        {
            return existingHeaders;
        }

        try
        {
            // Acquire token silently
            TokenRequestContext context = new(this._tokenScopes);
            AccessToken token = await this._tokenCredential.GetTokenAsync(context, cancellationToken).ConfigureAwait(false);

            // Create or copy headers and add Authorization
            Dictionary<string, string> headers = existingHeaders is not null
                ? new Dictionary<string, string>(existingHeaders)
                : [];

            headers["Authorization"] = $"Bearer {token.Token}";
            return headers;
        }
        catch (Exception)
        {
            // If silent auth fails, return original headers and let OAuth redirect handle it
            return existingHeaders;
        }
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
