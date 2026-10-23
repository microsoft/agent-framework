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
/// Provider-backed invocations create and dispose a separate MCP session for every call, including
/// <c>tools/list</c>, because provider authentication is not represented in the session cache key.
/// Without a provider, workflow invocations are cached by workflow session, server URL, label,
/// connection name, and explicit headers in a bounded least-recently-used cache. The bound includes
/// connecting and closing sessions. At capacity, an idle session is disposed before its replacement
/// connects. If every slot is busy, new scopes fail with <see cref="InvalidOperationException"/>;
/// existing scopes can still reuse their cached session.
/// Non-cancellation cleanup failures are reported through <see cref="Trace"/> warnings without replacing
/// the invocation result or error.
/// </remarks>
public sealed class DefaultMcpToolHandler : IWorkflowScopedMcpToolHandler, IAsyncDisposable
{
    private const int DefaultClientCacheMaxSize = 32;
    private const string FilenameAdditionalPropertyName = "filename";

    /// <summary>
    /// Reserved <c>toolName</c> value that maps an <see cref="IMcpToolHandler.InvokeToolAsync"/> request
    /// to the MCP protocol <c>tools/list</c> discovery operation.
    /// </summary>
    public const string ListToolsToolName = "tools/list";

    private static readonly JsonWriterOptions s_toolListJsonWriterOptions = new() { Indented = true };

    private readonly McpClientFactory _clientFactory;
    private readonly McpClientCache _clientCache;

    /// <summary>
    /// Initializes a new instance of the <see cref="DefaultMcpToolHandler"/> class.
    /// </summary>
    /// <param name="httpClientProvider">
    /// An optional callback that provides an <see cref="HttpClient"/> for each MCP server.
    /// The callback receives (serverUrl, cancellationToken) and should return an HttpClient
    /// configured with any required authentication. Return <see langword="null"/> to use a default HttpClient with no auth.
    /// <para>
    /// The callback is invoked for each tool invocation. MCP sessions are not cached when a callback is
    /// configured, even if it returns the same client or <see langword="null"/>. This adds session setup
    /// per call and does not preserve server-side session state between calls. Supplied HTTP clients
    /// remain caller-owned. Applications requiring session continuity should provide an
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
        : this(httpClientProvider, McpClientFactory.CreateHttpMessageHandler)
    {
    }

    internal DefaultMcpToolHandler(
        Func<string, CancellationToken, Task<HttpClient?>>? httpClientProvider,
        Func<HttpMessageHandler> httpMessageHandlerFactory,
        int clientCacheMaxSize = DefaultClientCacheMaxSize,
        Func<McpClientConnection, ValueTask>? clientConnectionDisposer = null)
    {
        McpClientLifetime lifetime = new();
        this._clientFactory = new(httpClientProvider, httpMessageHandlerFactory, lifetime);
        this._clientCache = new(this._clientFactory, lifetime, clientCacheMaxSize, clientConnectionDisposer);
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
        => await this.InvokeToolInWorkflowSessionAsync(
            serverUrl,
            serverLabel,
            toolName,
            arguments,
            headers,
            connectionName,
            workflowSessionId: string.Empty,
            cancellationToken).ConfigureAwait(false);

    /// <inheritdoc/>
    public async Task<McpServerToolResultContent> InvokeToolInWorkflowSessionAsync(
        string serverUrl,
        string? serverLabel,
        string toolName,
        IDictionary<string, object?>? arguments,
        IDictionary<string, string>? headers,
        string? connectionName,
        string workflowSessionId,
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

        if (this._clientFactory.HasHttpClientProvider)
        {
            return await this._clientFactory.InvokeProviderAsync(
                serverUrl, serverLabel, headers,
                client => InvokeClientAsync(client, toolName, arguments, cancellationToken),
                cancellationToken).ConfigureAwait(false);
        }

        return await this._clientCache.InvokeAsync(
            serverUrl, serverLabel, headers, connectionName, workflowSessionId,
            client => InvokeClientAsync(client, toolName, arguments, cancellationToken),
            cancellationToken).ConfigureAwait(false);
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
    /// Disposal is requested from an active provider-backed invocation, including a child execution context.
    /// Dispose the handler from its owning scope instead.
    /// </exception>
    public ValueTask DisposeAsync() => this._clientCache.DisposeAsync();

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
