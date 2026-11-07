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
/// Every invocation creates and disposes a separate MCP client, including <c>tools/list</c>.
/// Factory-created HTTP clients reuse factory-managed handlers without sharing MCP session state.
/// Standalone GET streams for unsolicited server messages are disabled; request-scoped SSE responses remain supported.
/// The handler owns no shared disposable resources. The host must await its invocations before disposing
/// the application-owned factory infrastructure.
/// Non-cancellation session and transport cleanup failures are reported through <see cref="Trace"/> warnings without replacing
/// the invocation result or error.
/// </remarks>
public sealed class DefaultMcpToolHandler : IMcpToolHandler
{
    private const string FilenameAdditionalPropertyName = "filename";

    /// <summary>
    /// Reserved <c>toolName</c> value that maps an <see cref="IMcpToolHandler.InvokeToolAsync"/> request
    /// to the MCP protocol <c>tools/list</c> discovery operation.
    /// </summary>
    public const string ListToolsToolName = "tools/list";

    private static readonly JsonWriterOptions s_toolListJsonWriterOptions = new() { Indented = true };

    private readonly IHttpClientFactory _httpClientFactory;
    private readonly string _httpClientName;

    /// <summary>
    /// Gets or initializes the protocol version requested for every invocation.
    /// </summary>
    /// <value>
    /// The protocol version to pass to the MCP SDK, or <see langword="null"/> to use its automatic negotiation.
    /// The default is <see langword="null"/>.
    /// </value>
    /// <remarks>
    /// Selecting a known legacy version skips the discovery probe but still initializes a separate session per invocation.
    /// Explicit selection restricts negotiation and fails if the server cannot satisfy the SDK's version requirements.
    /// Use separately configured handlers for servers requiring different protocol policies.
    /// </remarks>
    public string? ProtocolVersion { get; init; }

    /// <summary>
    /// Initializes a new instance of the <see cref="DefaultMcpToolHandler"/> class using an application-provided HTTP client factory.
    /// </summary>
    /// <param name="httpClientFactory">
    /// The factory that creates a separate <see cref="HttpClient"/> for every invocation.
    /// Factory-created clients are disposed after MCP cleanup; the factory and its pooled handlers remain application-owned.
    /// </param>
    /// <param name="httpClientName">
    /// The stable named-client configuration to use, or an empty string for the default configuration.
    /// Do not derive names from workflow identifiers, credentials, or arbitrary server URLs.
    /// </param>
    /// <remarks>
    /// The application is responsible for the HTTP pipeline's transport policy.
    /// Disable cookies and automatic redirects, enable certificate revocation checking, and restrict credential injection
    /// to the configured server origin. Pooled handlers must not retain per-invocation credentials or mutable origin state.
    /// Configure a finite handler lifetime so new invocations can pick up endpoint changes without disrupting active calls.
    /// </remarks>
    /// <exception cref="ArgumentNullException">A required argument is <see langword="null"/>.</exception>
    public DefaultMcpToolHandler(IHttpClientFactory httpClientFactory, string httpClientName)
    {
        this._httpClientFactory = Throw.IfNull(httpClientFactory);
        this._httpClientName = Throw.IfNull(httpClientName);
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

    private async Task<ClientConnection> CreateClientAsync(
        string serverUrl,
        string? serverLabel,
        IDictionary<string, string>? headers,
        CancellationToken cancellationToken)
    {
        Uri endpoint = new(serverUrl, UriKind.Absolute);
        HttpClientTransportOptions transportOptions = new()
        {
            Endpoint = endpoint,
            Name = serverLabel ?? "McpClient",
            AdditionalHeaders = headers,
            // Use Streamable HTTP rather than AutoDetect so the client does not negotiate down to the
            // legacy HTTP+SSE transport, which trusts a server-advertised message endpoint. That
            // server-controlled endpoint is the primary vector for redirecting the Authorization token
            // to a different origin; Streamable HTTP keeps every request on the configured origin.
            TransportMode = HttpTransportMode.StreamableHttp,
            EnableStandaloneGetStream = false
        };

        HttpClient httpClient = this._httpClientFactory.CreateClient(this._httpClientName);
        HttpClientTransport? transport = null;
        try
        {
            transport = new(transportOptions, httpClient, ownsHttpClient: true);
            McpClient client = await McpClient.CreateAsync(
                transport,
                new McpClientOptions { ProtocolVersion = this.ProtocolVersion },
                cancellationToken: cancellationToken).ConfigureAwait(false);
            return new ClientConnection(client, transport);
        }
        catch
        {
            if (transport is not null)
            {
                await DisposeResourceAsync(transport, "transport").ConfigureAwait(false);
            }
            else
            {
                httpClient.Dispose();
            }

            throw;
        }
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
