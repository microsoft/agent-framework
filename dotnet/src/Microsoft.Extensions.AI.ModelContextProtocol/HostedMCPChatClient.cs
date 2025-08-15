// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol.Client;

namespace Microsoft.Extensions.AI.ModelContextProtocol;

/// <summary>
/// Adds support for enabling MCP function invocation.
/// </summary>
public class HostedMCPChatClient : DelegatingChatClient
{
    private readonly ILoggerFactory? _loggerFactory;

    /// <summary>The logger to use for logging information about function invocation.</summary>
    private readonly ILogger _logger;

    /// <summary>The HTTP client to use when connecting to the remote MCP server.</summary>
    private readonly HttpClient _httpClient;

    /// <summary>A dictionary of cached mcp clients, keyed by the MCP server URL.</summary>
    private ConcurrentDictionary<string, IMcpClient>? _mcpClients = null;

    /// <summary>
    /// Initializes a new instance of the <see cref="HostedMCPChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying <see cref="IChatClient"/>, or the next instance in a chain of clients.</param>
    /// <param name="httpClient">The <see cref="HttpClient"/> to use when connecting to the remote MCP server.</param>
    /// <param name="loggerFactory">An <see cref="ILoggerFactory"/> to use for logging information about function invocation.</param>
    public HostedMCPChatClient(IChatClient innerClient, HttpClient httpClient, ILoggerFactory? loggerFactory = null)
        : base(innerClient)
    {
        this._loggerFactory = loggerFactory;
        this._logger = (ILogger?)loggerFactory?.CreateLogger<HostedMCPChatClient>() ?? NullLogger.Instance;
        this._httpClient = Throw.IfNull(httpClient);
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        if (options?.Tools is not { Count: > 0 })
        {
            // If there are no tools, just call the inner client.
            return await base.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);
        }

        var downstreamTools = await this.BuildDownstreamAIToolsAsync(options.Tools, cancellationToken).ConfigureAwait(false);
        options = options.Clone();
        options.Tools = downstreamTools;

        // Make the call to the inner client.
        return await base.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (options?.Tools is not { Count: > 0 })
        {
            // If there are no tools, just call the inner client.
            await foreach (var update in base.GetStreamingResponseAsync(messages, options, cancellationToken).ConfigureAwait(false))
            {
                yield return update;
            }
        }

        var downstreamTools = await this.BuildDownstreamAIToolsAsync(options!.Tools, cancellationToken).ConfigureAwait(false);
        options = options.Clone();
        options.Tools = downstreamTools;

        // Make the call to the inner client.
        await foreach (var update in base.GetStreamingResponseAsync(messages, options, cancellationToken).ConfigureAwait(false))
        {
            yield return update;
        }
    }

    private async Task<List<AITool>?> BuildDownstreamAIToolsAsync(IList<AITool>? inputTools, CancellationToken cancellationToken)
    {
        List<AITool>? downstreamTools = null;
        foreach (var tool in inputTools ?? [])
        {
            if (tool is HostedMcpServerTool mcpTool)
            {
                // List all MCP functions from the specified MCP server.
                // This will need some caching in a real-world scenario to avoid repeated calls.
                var mcpClient = await this.CreateMcpClientAsync(mcpTool.Url, mcpTool.ServerName).ConfigureAwait(false);
                var mcpFunctions = await mcpClient.ListToolsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);

                // Add the listed functions to our list of tools we'll pass to the inner client.
                foreach (var mcpFunction in mcpFunctions)
                {
                    if (mcpTool.AllowedTools is not null && !mcpTool.AllowedTools.Contains(mcpFunction.Name))
                    {
                        this._logger.LogInformation("MCP function '{FunctionName}' is not allowed by the tool configuration.", mcpFunction.Name);
                        continue;
                    }

                    downstreamTools ??= new List<AITool>();
                    switch (mcpTool.ApprovalMode)
                    {
                        case HostedMcpServerToolAlwaysRequireApprovalMode alwaysRequireApproval:
                            downstreamTools.Add(new ApprovalRequiredAIFunction(mcpFunction));
                            break;
                        case HostedMcpServerToolNeverRequireApprovalMode neverRequireApproval:
                            downstreamTools.Add(mcpFunction);
                            break;
                        case HostedMcpServerToolRequireSpecificApprovalMode specificApprovalMode when specificApprovalMode.AlwaysRequireApprovalToolNames?.Contains(mcpFunction.Name) is true:
                            downstreamTools.Add(new ApprovalRequiredAIFunction(mcpFunction));
                            break;
                        case HostedMcpServerToolRequireSpecificApprovalMode specificApprovalMode when specificApprovalMode.NeverRequireApprovalToolNames?.Contains(mcpFunction.Name) is true:
                            downstreamTools.Add(mcpFunction);
                            break;
                        default:
                            // Default to always require approval if no specific mode is set.
                            downstreamTools.Add(new ApprovalRequiredAIFunction(mcpFunction));
                            break;
                    }
                }

                // Skip adding the MCP tool itself, as we only want to add the functions it provides.
                continue;
            }

            // For other tools, we want to keep them in the list of tools.
            downstreamTools ??= new List<AITool>();
            downstreamTools.Add(tool);
        }

        return downstreamTools;
    }

    /// <inheritdoc/>
    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            // Dispose of the HTTP client if it was created by this client.
            this._httpClient?.Dispose();

            if (this._mcpClients is not null)
            {
                // Dispose of all cached MCP clients.
                foreach (var client in this._mcpClients.Values)
                {
#pragma warning disable CA2012 // Use ValueTasks correctly
                    _ = client.DisposeAsync();
#pragma warning restore CA2012 // Use ValueTasks correctly
                }

                this._mcpClients.Clear();
            }
        }

        base.Dispose(disposing);
    }

    private async Task<IMcpClient> CreateMcpClientAsync(Uri mcpServiceUri, string serverName)
    {
        if (this._mcpClients is null)
        {
            this._mcpClients = new ConcurrentDictionary<string, IMcpClient>(StringComparer.OrdinalIgnoreCase);
        }

        if (this._mcpClients.TryGetValue(mcpServiceUri.ToString(), out var cachedClient))
        {
            // Return the cached client if it exists.
            return cachedClient;
        }

#pragma warning disable CA2000 // Dispose objects before losing scope - This should be disposed by the mcp client.
        var transport = new SseClientTransport(new()
        {
            Endpoint = mcpServiceUri,
            Name = serverName,
        }, this._httpClient, this._loggerFactory);
#pragma warning restore CA2000 // Dispose objects before losing scope

        return await McpClientFactory.CreateAsync(transport).ConfigureAwait(false);
    }
}
