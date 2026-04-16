// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// An <see cref="IHostedService"/> that eagerly connects to the Foundry Toolsets MCP proxy at
/// container startup, discovers tools via <c>tools/list</c>, and caches them so they can be
/// injected into every <see cref="ChatOptions"/> by
/// <see cref="AgentFrameworkResponseHandler"/>.
/// </summary>
/// <remarks>
/// <para>
/// When <c>FOUNDRY_AGENT_TOOLSET_ENDPOINT</c> is absent the service starts without error and returns
/// an empty tool list, keeping the container healthy per spec §2.
/// </para>
/// <para>
/// Initialization is performed in <see cref="StartAsync"/> so the readiness probe is only satisfied
/// after all configured toolsets are connected and their tools discovered (spec §3.1 SHOULD).
/// </para>
/// </remarks>
public sealed class FoundryToolboxService : IHostedService, IAsyncDisposable
{
    private readonly FoundryToolboxOptions _options;
    private readonly TokenCredential _credential;
    private readonly ILogger<FoundryToolboxService> _logger;

    private readonly List<McpClient> _clients = [];
    private readonly List<HttpClient> _httpClients = [];

    /// <summary>
    /// Gets the cached list of <see cref="AITool"/> instances discovered from all connected toolsets.
    /// Always non-null after startup; returns an empty list when no toolset endpoint is configured.
    /// </summary>
    public IReadOnlyList<AITool> Tools { get; private set; } = [];

    /// <summary>
    /// Initializes a new instance of <see cref="FoundryToolboxService"/>.
    /// </summary>
    public FoundryToolboxService(
        IOptions<FoundryToolboxOptions> options,
        TokenCredential credential,
        ILogger<FoundryToolboxService>? logger = null)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(credential);

        this._options = options.Value;
        this._credential = credential;
        this._logger = logger ?? NullLogger<FoundryToolboxService>.Instance;
    }

    /// <inheritdoc/>
    public async Task StartAsync(CancellationToken cancellationToken)
    {
        var endpoint = this._options.EndpointOverride
            ?? Environment.GetEnvironmentVariable("FOUNDRY_AGENT_TOOLSET_ENDPOINT");

        if (string.IsNullOrEmpty(endpoint))
        {
            this._logger.LogInformation("FOUNDRY_AGENT_TOOLSET_ENDPOINT is not set; toolbox support is disabled.");
            this.Tools = [];
            return;
        }

        if (this._options.ToolsetNames.Count == 0)
        {
            this._logger.LogInformation("No toolset names configured; toolbox support is disabled.");
            this.Tools = [];
            return;
        }

        var featuresHeader = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_TOOLSET_FEATURES");
        var agentName = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_NAME") ?? "hosted-agent";
        var agentVersion = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_VERSION") ?? "1.0.0";

        var allTools = new List<AITool>();

        // Deduplicate toolset names to avoid duplicate MCP clients and ambiguous tool exposure
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var toolsetName in this._options.ToolsetNames)
        {
            if (!seen.Add(toolsetName))
            {
                continue;
            }

            var proxyUrl = $"{endpoint.TrimEnd('/')}/{toolsetName}/mcp?api-version={this._options.ApiVersion}";

            if (this._logger.IsEnabled(LogLevel.Information))
            {
                this._logger.LogInformation("Connecting to toolset '{ToolsetName}' at {ProxyUrl}.", toolsetName, proxyUrl);
            }

            try
            {
                var handler = new FoundryToolboxBearerTokenHandler(this._credential, featuresHeader)
                {
                    InnerHandler = new HttpClientHandler()
                };

                var httpClient = new HttpClient(handler);
                this._httpClients.Add(httpClient);

                var transportOptions = new HttpClientTransportOptions
                {
                    Endpoint = new Uri(proxyUrl),
                    Name = toolsetName,
                };

                var transport = new HttpClientTransport(transportOptions, httpClient);

                var clientOptions = new McpClientOptions
                {
                    ClientInfo = new()
                    {
                        Name = agentName,
                        Version = agentVersion
                    }
                };

                var client = await McpClient.CreateAsync(
                    transport,
                    clientOptions,
                    cancellationToken: cancellationToken).ConfigureAwait(false);

                this._clients.Add(client);

                var tools = await client.ListToolsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);

                if (this._logger.IsEnabled(LogLevel.Information))
                {
                    this._logger.LogInformation(
                        "Toolset '{ToolsetName}': discovered {ToolCount} tool(s).",
                        toolsetName,
                        tools.Count);
                }

                foreach (var tool in tools)
                {
                    allTools.Add(new ConsentAwareMcpClientTool(tool, toolsetName));
                }
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                this._logger.LogError(
                    ex,
                    "Failed to connect to toolset '{ToolsetName}'. Tools from this toolset will not be available.",
                    toolsetName);
            }
        }

        this.Tools = allTools;
    }

    /// <inheritdoc/>
    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    /// <inheritdoc/>
    public async ValueTask DisposeAsync()
    {
        foreach (var client in this._clients)
        {
            await client.DisposeAsync().ConfigureAwait(false);
        }

        this._clients.Clear();

        foreach (var httpClient in this._httpClients)
        {
            httpClient.Dispose();
        }

        this._httpClients.Clear();
    }
}
