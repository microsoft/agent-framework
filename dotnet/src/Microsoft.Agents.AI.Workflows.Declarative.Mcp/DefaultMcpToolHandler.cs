// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI.Workflows.Declarative.Mcp;

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
    private const string FilenameAdditionalPropertyName = "filename";

    /// <summary>
    /// Reserved <c>toolName</c> value that maps an <see cref="IMcpToolHandler.InvokeToolAsync"/> request
    /// to the MCP protocol <c>tools/list</c> discovery operation.
    /// </summary>
    public const string ListToolsToolName = "tools/list";

    private static readonly JsonWriterOptions s_toolListJsonWriterOptions = new() { Indented = true };

    private readonly Func<string, CancellationToken, Task<HttpClient?>>? _httpClientProvider;
    private readonly Dictionary<(string Url, string Label, string Connection, string HeadersHash), McpClient> _clients = [];
    private readonly Dictionary<string, HttpClient> _ownedHttpClients = [];
    private readonly SemaphoreSlim _clientLock = new(1, 1);

    /// <summary>
    /// Initializes a new instance of the <see cref="DefaultMcpToolHandler"/> class.
    /// </summary>
    /// <param name="httpClientProvider">
    /// An optional callback that provides an <see cref="HttpClient"/> for each MCP server.
    /// The callback receives (serverUrl, cancellationToken) and should return an HttpClient
    /// configured with any required authentication. Return <see langword="null"/> to use a default HttpClient with no auth.
    /// <para>
    /// Security: HttpClients created by this handler pin credential headers to the configured server
    /// origin and disable auto-redirect. When you supply your own <see cref="HttpClient"/>, you are
    /// responsible for equivalent protection — attach credentials only for the configured server origin
    /// (for example via a <see cref="DelegatingHandler"/>) so a server-advertised endpoint or redirect on
    /// a different origin cannot capture the Authorization token.
    /// </para>
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
        if (IsListToolsToolName(toolName))
        {
            ThrowIfListToolsArgumentsSpecified(arguments);
            McpClient listToolsClient = await this.GetOrCreateClientAsync(serverUrl, serverLabel, headers, connectionName, cancellationToken).ConfigureAwait(false);
            IList<McpClientTool> tools = await listToolsClient.ListToolsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
            return CreateListToolsResultContent(tools.Select(tool => tool.ProtocolTool));
        }

        McpClient client = await this.GetOrCreateClientAsync(serverUrl, serverLabel, headers, connectionName, cancellationToken).ConfigureAwait(false);

        McpServerToolResultContent resultContent = new(Guid.NewGuid().ToString());

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

    internal static bool IsListToolsToolName(string toolName) =>
        string.Equals(toolName, ListToolsToolName, StringComparison.Ordinal);

    internal static McpServerToolResultContent CreateListToolsResultContent(IEnumerable<Tool> tools)
    {
        Throw.IfNull(tools);

        McpServerToolResultContent resultContent = new(Guid.NewGuid().ToString())
        {
            Outputs = []
        };

        resultContent.Outputs.Add(new TextContent(SerializeToolsList(tools)));

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
        string? connectionName,
        CancellationToken cancellationToken)
    {
        string trimmedUrl = serverUrl.Trim();
        var clientCacheKey = BuildCacheKey(trimmedUrl, serverLabel, connectionName, headers);

        await this._clientLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (this._clients.TryGetValue(clientCacheKey, out McpClient? existingClient))
            {
                return existingClient;
            }

            McpClient newClient = await this.CreateClientAsync(trimmedUrl, serverLabel, headers, trimmedUrl, cancellationToken).ConfigureAwait(false);
            this._clients[clientCacheKey] = newClient;
            return newClient;
        }
        finally
        {
            this._clientLock.Release();
        }
    }

    /// <summary>
    /// Builds the per-client cache key as a 4-tuple of
    /// (trimmed serverUrl, serverLabel, connectionName, headers hash). All four components
    /// participate so that callers using different labels/connections/headers receive
    /// distinct <see cref="McpClient"/> instances even when targeting the same URL.
    /// </summary>
    internal static (string Url, string Label, string Connection, string HeadersHash) BuildCacheKey(
        string trimmedUrl,
        string? serverLabel,
        string? connectionName,
        IDictionary<string, string>? headers) =>
        (trimmedUrl, serverLabel ?? string.Empty, connectionName ?? string.Empty, ComputeHeadersHash(headers));

    private async Task<McpClient> CreateClientAsync(
        string serverUrl,
        string? serverLabel,
        IDictionary<string, string>? headers,
        string httpClientCacheKey,
        CancellationToken cancellationToken)
    {
        // Get or create HttpClient (Can be shared across McpClients for the same server)
        HttpClient? httpClient = null;

        if (this._httpClientProvider is not null)
        {
            httpClient = await this._httpClientProvider(serverUrl, cancellationToken).ConfigureAwait(false);
        }

        if (httpClient is null && !this._ownedHttpClients.TryGetValue(httpClientCacheKey, out httpClient))
        {
            // Disable cookies so handler-level state (cookie jar) cannot cross the cache-key
            // isolation boundary established by GetOrCreateClientAsync. The actual MCP auth
            // travels via AdditionalHeaders (set per-transport below), not session cookies.
            // Disable auto-redirect so an HTTP redirect cannot carry credential headers to a
            // different origin (defense-in-depth alongside the origin pinning applied below).
            // CheckCertificateRevocationList satisfies CA5399 since we're explicitly constructing the handler.
            HttpClientHandler handler = new()
            {
                UseCookies = false,
                AllowAutoRedirect = false,
                CheckCertificateRevocationList = true
            };

            // Pin credential headers to the configured server origin as defense-in-depth. Forcing
            // StreamableHttp (below) already removes the primary vector (a server-advertised cross-origin
            // SSE message endpoint), and AllowAutoRedirect=false blocks auto-redirects. This handler is the
            // backstop: it guarantees the Authorization token and other credentials never leave the pinned
            // origin even if a future change re-enables AutoDetect or redirects, or the SDK constructs a
            // request to a new URI (AdditionalHeaders are re-stamped by the transport, so HttpClient's own
            // redirect header-stripping does not cover them).
            OriginPinningHandler pinningHandler = new(new Uri(serverUrl)) { InnerHandler = handler };
            httpClient = new HttpClient(pinningHandler);
            this._ownedHttpClients[httpClientCacheKey] = httpClient;
        }

        HttpClientTransportOptions transportOptions = new()
        {
            Endpoint = new Uri(serverUrl),
            Name = serverLabel ?? "McpClient",
            AdditionalHeaders = headers,
            // Use Streamable HTTP rather than AutoDetect so the client does not negotiate down to the
            // legacy HTTP+SSE transport, which trusts a server-advertised message endpoint. That
            // server-controlled endpoint is the primary vector for redirecting the Authorization token
            // to a different origin; Streamable HTTP keeps every request on the configured origin.
            TransportMode = HttpTransportMode.StreamableHttp
        };

        HttpClientTransport transport = new(transportOptions, httpClient);

        return await McpClient.CreateAsync(transport, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Computes a deterministic, order-independent hash of the header set.
    /// Header names are lower-cased for case-insensitive matching (RFC 7230 §3.2).
    /// Header values remain case-sensitive (RFC 7235 — credentials are case-sensitive).
    /// </summary>
#pragma warning disable CA1308 // RFC 7230 §3.2 requires lower-cased header names for case-insensitive comparison; CA1308's uppercase preference does not apply here
    internal static string ComputeHeadersHash(IDictionary<string, string>? headers)
    {
        if (headers is null || headers.Count == 0)
        {
            return string.Empty;
        }

        // Sort by lower-cased key for deterministic ordering, preserving value case.
        SortedDictionary<string, string> sorted = new(StringComparer.Ordinal);
        foreach (KeyValuePair<string, string> header in headers)
        {
            sorted[header.Key.ToLowerInvariant()] = header.Value;
        }

        StringBuilder payload = new();
        foreach (KeyValuePair<string, string> kvp in sorted)
        {
            payload.Append(kvp.Key).Append(':').Append(kvp.Value).Append('\n');
        }

        byte[] inputBytes = Encoding.UTF8.GetBytes(payload.ToString());
#if NET5_0_OR_GREATER
        byte[] hashBytes = SHA256.HashData(inputBytes);
#else
        using SHA256 sha256 = SHA256.Create();
        byte[] hashBytes = sha256.ComputeHash(inputBytes);
#endif

        // Convert to hex string (compatible with net472/netstandard2.0)
        StringBuilder hex = new(hashBytes.Length * 2);
        foreach (byte b in hashBytes)
        {
            hex.Append(b.ToString("X2", System.Globalization.CultureInfo.InvariantCulture));
        }

        return hex.ToString();
    }
#pragma warning restore CA1308

    private static void ThrowIfListToolsArgumentsSpecified(IDictionary<string, object?>? arguments)
    {
        if (arguments is { Count: > 0 })
        {
            throw new ArgumentException(
                $"The reserved MCP '{ListToolsToolName}' operation does not accept tool arguments.",
                nameof(arguments));
        }
    }

    private static void PopulateResultContent(McpServerToolResultContent resultContent, CallToolResult result)
    {
        // Ensure Outputs list is initialized
        resultContent.Outputs ??= [];

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

            resultContent.Outputs.Add(new TextContent($"Error: {errorText ?? "Unknown error from MCP Server call"}"));
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
                resultContent.Outputs.Add(content);
            }
        }
    }

    internal static AIContent ConvertContentBlock(ContentBlock block)
    {
        // Delegate to the MCP SDK's canonical converter. It maps every known
        // ContentBlock subtype (Text/Image/Audio/EmbeddedResource/ToolUse/ToolResult)
        // and sets RawRepresentation + AdditionalProperties from block.Meta.
        // It intentionally returns null for ResourceLinkBlock — map that to
        // UriContent here so callers always receive a usable AIContent.
        return block.ToAIContent() ?? block switch
        {
            ResourceLinkBlock link => new UriContent(link.Uri, link.MimeType ?? "application/octet-stream")
            {
                RawRepresentation = link,
                AdditionalProperties = CreateAdditionalProperties(link),
            },
            _ => new TextContent(block.ToString() ?? string.Empty)
            {
                RawRepresentation = block,
                AdditionalProperties = CreateAdditionalProperties(block),
            },
        };
    }

    private static AdditionalPropertiesDictionary? CreateAdditionalProperties(ContentBlock block)
    {
        AdditionalPropertiesDictionary? properties = null;

        if (block.Meta is not null)
        {
            foreach (var property in block.Meta)
            {
                properties ??= new AdditionalPropertiesDictionary();
                properties.Add(property.Key, property.Value);
            }
        }

        if (block is ResourceLinkBlock { Name: { Length: > 0 } name })
        {
            properties ??= new AdditionalPropertiesDictionary();
            properties.TryAdd(FilenameAdditionalPropertyName, name);
        }

        return properties;
    }

    private static string SerializeToolsList(IEnumerable<Tool> tools)
    {
        using MemoryStream stream = new();
        using (Utf8JsonWriter writer = new(stream, s_toolListJsonWriterOptions))
        {
            writer.WriteStartObject();
            writer.WriteStartArray("tools");

            foreach (Tool tool in tools)
            {
                writer.WriteStartObject();
                writer.WriteString("name", tool.Name);
                writer.WriteString("description", tool.Description);
                writer.WritePropertyName("inputSchema");
                tool.InputSchema.WriteTo(writer);
                writer.WritePropertyName("outputSchema");
                if (tool.OutputSchema is JsonElement outputSchema)
                {
                    outputSchema.WriteTo(writer);
                }
                else
                {
                    writer.WriteNullValue();
                }

                writer.WriteEndObject();
            }

            writer.WriteEndArray();
            writer.WriteEndObject();
        }

        return Encoding.UTF8.GetString(stream.GetBuffer(), 0, (int)stream.Length);
    }
}

/// <summary>
/// A <see cref="DelegatingHandler"/> that strips credential-bearing headers from any outbound request
/// whose origin does not match the origin the MCP client was configured with.
/// </summary>
/// <remarks>
/// <para>
/// This pins the Authorization token (and other credential headers) to the trusted server origin so a
/// compromised or malicious MCP server cannot redirect them to a different origin — for example by
/// advertising a cross-origin SSE message endpoint or issuing an HTTP redirect. Same-origin requests are
/// left untouched so legitimate MCP traffic continues to carry its credentials.
/// </para>
/// <para>
/// This is a defense-in-depth control. Using <see cref="HttpTransportMode.StreamableHttp"/> already removes
/// the primary vector (a server-advertised cross-origin message endpoint) and disabling auto-redirect blocks
/// redirect-based leakage; this handler backstops both so credentials stay pinned even if those settings
/// change or the SDK builds a request to a new URI (<c>AdditionalHeaders</c> are re-stamped by the transport
/// and are therefore not covered by <see cref="HttpClient"/>'s own redirect header-stripping).
/// </para>
/// <para>
/// Caveat for future maintainers: this strips credentials on <em>every</em> cross-origin request. That is safe
/// today because <see cref="DefaultMcpToolHandler"/> carries auth via static request headers, not the SDK's
/// built-in OAuth flow. If OAuth support is ever added here, requests to the authorization server (a different
/// origin than the MCP resource server) legitimately carry credentials, so those auth-server origins would need
/// to be allow-listed to avoid breaking the token exchange.
/// </para>
/// </remarks>
internal sealed class OriginPinningHandler : DelegatingHandler
{
    // Credential-bearing headers that must never cross the pinned-origin boundary.
    private static readonly string[] s_credentialHeaderNames =
    [
        "Authorization",
        "Proxy-Authorization",
        "Cookie",
    ];

    private readonly Uri _pinnedEndpoint;

    /// <summary>
    /// Initializes a new instance of the <see cref="OriginPinningHandler"/> class.
    /// </summary>
    /// <param name="pinnedEndpoint">The configured MCP server endpoint whose origin credentials are pinned to. Must be an absolute URI.</param>
    public OriginPinningHandler(Uri pinnedEndpoint)
    {
        Throw.IfNull(pinnedEndpoint);
        if (!pinnedEndpoint.IsAbsoluteUri)
        {
            throw new ArgumentException("The pinned endpoint must be an absolute URI.", nameof(pinnedEndpoint));
        }

        this._pinnedEndpoint = pinnedEndpoint;
    }

    /// <inheritdoc/>
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        StripCredentialHeadersOnCrossOrigin(request, this._pinnedEndpoint);
        return base.SendAsync(request, cancellationToken);
    }

    /// <summary>
    /// Removes credential headers from <paramref name="request"/> when its origin differs from that of
    /// <paramref name="pinnedEndpoint"/>. Same-origin requests are left untouched. Origin comparison covers
    /// scheme, host, and port (case-insensitive) via <see cref="Uri.Compare"/>, which normalizes default
    /// ports so an explicit default port (for example <c>:443</c> for https) matches an omitted one. A
    /// relative request URI is resolved by <see cref="HttpClient"/> against its base address (the pinned
    /// origin) and so can never target a different origin; its headers are left untouched.
    /// </summary>
    internal static void StripCredentialHeadersOnCrossOrigin(HttpRequestMessage request, Uri pinnedEndpoint)
    {
        Throw.IfNull(request);
        Throw.IfNull(pinnedEndpoint);

        if (request.RequestUri is not { IsAbsoluteUri: true } requestUri)
        {
            return;
        }

        if (Uri.Compare(requestUri, pinnedEndpoint, UriComponents.SchemeAndServer, UriFormat.Unescaped, StringComparison.OrdinalIgnoreCase) == 0)
        {
            return;
        }

        foreach (string headerName in s_credentialHeaderNames)
        {
            request.Headers.Remove(headerName);
        }
    }
}
