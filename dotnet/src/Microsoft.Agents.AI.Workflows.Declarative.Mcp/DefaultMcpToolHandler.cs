// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
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
/// Every invocation creates and disposes a separate MCP client, including <c>tools/list</c>.
/// Handler-created HTTP clients reuse an underlying HTTP handler without sharing MCP session state.
/// Non-cancellation session and transport cleanup failures are reported through <see cref="Trace"/> warnings without replacing
/// the invocation result or error.
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
    private readonly Lazy<HttpMessageInvoker> _httpMessageInvoker;
    private readonly object _invocationLock = new();
    private readonly AsyncLocal<InvocationScope?> _currentInvocation = new();
    private TaskCompletionSource<bool>? _invocationsDrained;
    private int _activeInvocations;
    private bool _disposing;

    /// <summary>
    /// Initializes a new instance of the <see cref="DefaultMcpToolHandler"/> class.
    /// </summary>
    /// <param name="httpClientProvider">
    /// An optional callback that provides an <see cref="HttpClient"/> for each MCP server.
    /// The callback receives (serverUrl, cancellationToken) and should return an HttpClient
    /// configured with any required authentication. Return <see langword="null"/> to use a default HttpClient with no auth.
    /// <para>
    /// The callback is invoked for each tool invocation. MCP sessions are not cached when a callback is
    /// configured, even if it returns the same client or <see langword="null"/>. MCP clients are also
    /// invocation-scoped without a callback; server-side session state is not preserved between calls.
    /// Supplied HTTP clients remain caller-owned. Applications requiring session continuity should provide an
    /// <see cref="IMcpToolHandler"/> with an explicitly scoped authentication and session lifetime.
    /// </para>
    /// <para>
    /// Security: HttpClients created by this handler pin credential headers to the configured server
    /// origin and disable auto-redirect. When you supply your own <see cref="HttpClient"/>, you are
    /// responsible for equivalent protection — attach credentials only for the configured server origin
    /// (for example via a <see cref="DelegatingHandler"/>) so a server-advertised endpoint or redirect on
    /// a different origin cannot capture the Authorization token.
    /// </para>
    /// </param>
    public DefaultMcpToolHandler(Func<string, CancellationToken, Task<HttpClient?>>? httpClientProvider = null)
        : this(httpClientProvider, CreateHttpMessageHandler)
    {
    }

    internal DefaultMcpToolHandler(
        Func<string, CancellationToken, Task<HttpClient?>>? httpClientProvider,
        Func<HttpMessageHandler> httpMessageHandlerFactory)
    {
        this._httpClientProvider = httpClientProvider;
        Throw.IfNull(httpMessageHandlerFactory);
        this._httpMessageInvoker = new(() => new HttpMessageInvoker(httpMessageHandlerFactory(), disposeHandler: true));
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
        }

        if (headers is not null)
        {
            foreach (KeyValuePair<string, string> header in headers)
            {
                HttpHeaderValidation.ValidateNoProhibitedCharacters(
                    header.Key,
                    nameof(headers),
                    "HTTP header name contains invalid characters.");
                HttpHeaderValidation.ValidateNoProhibitedCharacters(
                    header.Value,
                    nameof(headers),
                    "HTTP header value contains invalid characters.");
            }
        }

        cancellationToken.ThrowIfCancellationRequested();
        using InvocationScope invocation = this.EnterInvocation();
        ClientConnection connection = await this.CreateClientAsync(
            serverUrl.Trim(), serverLabel, headers, cancellationToken).ConfigureAwait(false);
        await using (connection.ConfigureAwait(false))
        {
            return await InvokeClientAsync(connection.Client, toolName, arguments, cancellationToken).ConfigureAwait(false);
        }
    }

    private static async Task<McpServerToolResultContent> InvokeClientAsync(
        McpClient client,
        string toolName,
        IDictionary<string, object?>? arguments,
        CancellationToken cancellationToken)
    {
        if (IsListToolsToolName(toolName))
        {
            IList<McpClientTool> tools = await client.ListToolsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
            return CreateListToolsResultContent(tools.Select(tool => tool.ProtocolTool));
        }

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
    /// <exception cref="InvalidOperationException">
    /// Disposal is requested from an active MCP invocation, including a child execution context.
    /// Dispose the handler from its owning scope instead.
    /// </exception>
    public async ValueTask DisposeAsync()
    {
        for (InvocationScope? context = this._currentInvocation.Value; context is not null; context = context.Parent)
        {
            if (!context.Completion.IsCompleted)
            {
                throw new InvalidOperationException("Cannot dispose the MCP handler from an active MCP invocation.");
            }
        }

        Task? invocations;
        lock (this._invocationLock)
        {
            this.ThrowIfDisposing();
            this._disposing = true;
            invocations = this._invocationsDrained?.Task;
        }

        if (invocations is not null)
        {
            await invocations.ConfigureAwait(false);
        }

        if (this._httpMessageInvoker.IsValueCreated)
        {
            this._httpMessageInvoker.Value.Dispose();
        }
    }

    [System.Diagnostics.CodeAnalysis.SuppressMessage("Maintainability", "CA1513:Use ObjectDisposedException throw helper",
        Justification = "The helper is not available on .NET Framework or .NET Standard 2.0.")]
    private void ThrowIfDisposing()
    {
        if (this._disposing)
        {
            throw new ObjectDisposedException(nameof(DefaultMcpToolHandler));
        }
    }

    private InvocationScope EnterInvocation()
    {
        lock (this._invocationLock)
        {
            this.ThrowIfDisposing();
            if (this._activeInvocations++ == 0)
            {
                this._invocationsDrained = new(TaskCreationOptions.RunContinuationsAsynchronously);
            }
        }

        InvocationScope invocation = new(this, this._currentInvocation.Value);
        this._currentInvocation.Value = invocation;
        return invocation;
    }

    private async Task<ClientConnection> CreateClientAsync(
        string serverUrl,
        string? serverLabel,
        IDictionary<string, string>? headers,
        CancellationToken cancellationToken)
    {
        Uri endpoint = new(serverUrl, UriKind.Absolute);
        HttpClient? httpClient = null;
        if (this._httpClientProvider is not null)
        {
            httpClient = await this._httpClientProvider(serverUrl, cancellationToken).ConfigureAwait(false);
        }

        bool ownsHttpClient = httpClient is null;
        if (httpClient is null)
        {
            // Pin credential headers to the configured server origin as defense-in-depth. Forcing
            // StreamableHttp (below) already removes the primary vector (a server-advertised cross-origin
            // SSE message endpoint), and AllowAutoRedirect=false blocks auto-redirects. This handler is the
            // backstop: it guarantees the Authorization token and other credentials never leave the pinned
            // origin even if a future change re-enables AutoDetect or redirects, or the SDK constructs a
            // request to a new URI (AdditionalHeaders are re-stamped by the transport, so HttpClient's own
            // redirect header-stripping does not cover them).
            // Caveat for future maintainers: the handler strips credentials on every cross-origin request.
            // That is safe today because this handler carries auth via static request headers, not the
            // SDK's built-in OAuth flow. If OAuth support is ever added here, requests to the authorization
            // server (a different origin than the MCP resource server) legitimately carry credentials, so
            // those auth-server origins would need to be allow-listed to avoid breaking the token exchange.
            OriginPinningHandler pinningHandler = new(endpoint)
            {
                InnerHandler = new SharedHttpMessageHandler(this._httpMessageInvoker.Value)
            };
            httpClient = new HttpClient(pinningHandler);
        }

        HttpClientTransportOptions transportOptions = new()
        {
            Endpoint = endpoint,
            Name = serverLabel ?? "McpClient",
            AdditionalHeaders = headers,
            // Use Streamable HTTP rather than AutoDetect so the client does not negotiate down to the
            // legacy HTTP+SSE transport, which trusts a server-advertised message endpoint. That
            // server-controlled endpoint is the primary vector for redirecting the Authorization token
            // to a different origin; Streamable HTTP keeps every request on the configured origin.
            TransportMode = HttpTransportMode.StreamableHttp
        };

        HttpClientTransport? transport = null;
        try
        {
            transport = new(transportOptions, httpClient, ownsHttpClient: ownsHttpClient);
            McpClient client = await McpClient.CreateAsync(transport, cancellationToken: cancellationToken).ConfigureAwait(false);
            return new ClientConnection(client, transport);
        }
        catch
        {
            if (transport is not null)
            {
                await DisposeResourceAsync(transport, "transport").ConfigureAwait(false);
            }
            else if (ownsHttpClient)
            {
                httpClient?.Dispose();
            }

            throw;
        }
    }

    private static HttpMessageHandler CreateHttpMessageHandler() =>
        new HttpClientHandler
        {
            // Keep cookies out of pooled transport state and prevent credential-bearing redirects.
            UseCookies = false,
            AllowAutoRedirect = false,
            CheckCertificateRevocationList = true
        };

    private sealed class InvocationScope(DefaultMcpToolHandler owner, InvocationScope? parent) : IDisposable
    {
        private readonly TaskCompletionSource<bool> _completion = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task Completion => this._completion.Task;

        public InvocationScope? Parent { get; } = parent;

        public void Dispose()
        {
            lock (owner._invocationLock)
            {
                this._completion.SetResult(true);
                if (--owner._activeInvocations == 0)
                {
                    owner._invocationsDrained!.SetResult(true);
                }
            }

            owner._currentInvocation.Value = this.Parent;
        }
    }

    // Each invocation disposes its own pipeline without disposing the handler-owned connection pool.
    private sealed class SharedHttpMessageHandler(HttpMessageInvoker invoker) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            invoker.SendAsync(request, cancellationToken);
    }

    internal sealed class ClientConnection(McpClient client, IAsyncDisposable transport) : IAsyncDisposable
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
                // McpClient owns the connected session, not the reusable transport factory.
                await DisposeResourceAsync(transport, "transport").ConfigureAwait(false);
            }
        }
    }

    private static async ValueTask DisposeResourceAsync<T>(T resource, string resourceName)
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
