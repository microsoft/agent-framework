// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Microsoft.Shared.DiagnosticIds;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// An <see cref="IHostedService"/> that eagerly connects to the Foundry Toolboxes MCP proxy at
/// container startup, discovers tools via <c>tools/list</c>, and caches them so they can be
/// injected into every <see cref="ChatOptions"/> by <see cref="AgentFrameworkResponseHandler"/>.
/// </summary>
/// <remarks>
/// <para>
/// When <c>FOUNDRY_AGENT_TOOLSET_ENDPOINT</c> is absent the service starts without error and
/// no tools are registered, keeping the container healthy per spec §2.
/// </para>
/// <para>
/// Startup eagerly connects to every name in <see cref="FoundryToolboxOptions.ToolboxNames"/>.
/// Beyond those, per-request toolbox markers (see <see cref="HostedMcpToolboxAITool"/>) are
/// resolved at request time through <see cref="GetToolboxToolsAsync"/>. Unknown toolboxes are
/// rejected when <see cref="FoundryToolboxOptions.StrictMode"/> is <see langword="true"/> and
/// lazily connected otherwise.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public sealed class FoundryToolboxService : IHostedService, IAsyncDisposable
{
    private readonly FoundryToolboxOptions _options;
    private readonly TokenCredential _credential;
    private readonly ILogger<FoundryToolboxService> _logger;

    private readonly Dictionary<string, CachedToolbox> _toolboxes = new(StringComparer.OrdinalIgnoreCase);
    private readonly SemaphoreSlim _lazyOpenLock = new(1, 1);

    private string? _resolvedEndpoint;
    private string? _featuresHeader;
    private string _agentName = "hosted-agent";
    private string _agentVersion = "1.0.0";

    /// <summary>
    /// Gets the cached list of <see cref="AITool"/> instances discovered from all
    /// pre-registered toolboxes. Always non-null after startup.
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
        this._resolvedEndpoint = this._options.EndpointOverride
            ?? Environment.GetEnvironmentVariable("FOUNDRY_AGENT_TOOLSET_ENDPOINT");

        if (string.IsNullOrEmpty(this._resolvedEndpoint))
        {
            this._logger.LogInformation("FOUNDRY_AGENT_TOOLSET_ENDPOINT is not set; toolbox support is disabled.");
            this.Tools = [];
            return;
        }

        this._featuresHeader = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_TOOLSET_FEATURES");
        this._agentName = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_NAME") ?? "hosted-agent";
        this._agentVersion = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_VERSION") ?? "1.0.0";

        if (this._options.ToolboxNames.Count == 0)
        {
            this._logger.LogInformation("No pre-registered toolbox names configured.");
            this.Tools = [];
            return;
        }

        var allTools = new List<AITool>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var toolboxName in this._options.ToolboxNames)
        {
            if (!seen.Add(toolboxName))
            {
                continue;
            }

            try
            {
                var cached = await this.OpenToolboxAsync(toolboxName, version: null, cancellationToken).ConfigureAwait(false);
                this._toolboxes[toolboxName] = cached;
                allTools.AddRange(cached.Tools);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                if (this._logger.IsEnabled(LogLevel.Error))
                {
                    this._logger.LogError(
                        ex,
                        "Failed to connect to toolbox '{ToolboxName}'. Tools from this toolbox will not be available.",
                        toolboxName);
                }
            }
        }

        this.Tools = allTools;
    }

    /// <summary>
    /// Resolves the tools for a per-request toolbox marker. Returns cached tools when the
    /// toolbox has already been opened; otherwise honors
    /// <see cref="FoundryToolboxOptions.StrictMode"/> to either reject or lazily open it.
    /// </summary>
    /// <param name="toolboxName">The Foundry toolbox name from the marker.</param>
    /// <param name="version">
    /// Optional pinned version. Currently reserved for future use — version-specific routing is
    /// handled server-side by the Foundry proxy. This parameter is accepted for forward compatibility
    /// but does not affect the proxy URL used to connect to the toolbox.
    /// </param>
    /// <param name="cancellationToken">The request cancellation token.</param>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the toolbox is not pre-registered and <see cref="FoundryToolboxOptions.StrictMode"/>
    /// is <see langword="true"/>, or when the toolbox endpoint is not configured.
    /// </exception>
    public async ValueTask<IReadOnlyList<AITool>> GetToolboxToolsAsync(
        string toolboxName,
        string? version,
        CancellationToken cancellationToken)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(toolboxName);

        if (this._toolboxes.TryGetValue(toolboxName, out var cached))
        {
            return cached.Tools;
        }

        if (this._options.StrictMode)
        {
            throw new InvalidOperationException(
                $"Toolbox '{toolboxName}' is not pre-registered via AddFoundryToolboxes(...). " +
                $"Either register it at startup or set {nameof(FoundryToolboxOptions.StrictMode)}=false to allow lazy resolution.");
        }

        if (string.IsNullOrEmpty(this._resolvedEndpoint))
        {
            throw new InvalidOperationException(
                $"Cannot resolve toolbox '{toolboxName}': FOUNDRY_AGENT_TOOLSET_ENDPOINT is not set.");
        }

        await this._lazyOpenLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            // Double-check after acquiring the lock to avoid duplicate opens under concurrency.
            if (this._toolboxes.TryGetValue(toolboxName, out cached))
            {
                return cached.Tools;
            }

            cached = await this.OpenToolboxAsync(toolboxName, version, cancellationToken).ConfigureAwait(false);
            this._toolboxes[toolboxName] = cached;
            return cached.Tools;
        }
        finally
        {
            this._lazyOpenLock.Release();
        }
    }

    private async Task<CachedToolbox> OpenToolboxAsync(
        string toolboxName,
        string? version,
        CancellationToken cancellationToken)
    {
        var proxyUrl = $"{this._resolvedEndpoint!.TrimEnd('/')}/{toolboxName}/mcp?api-version={this._options.ApiVersion}";

        if (this._logger.IsEnabled(LogLevel.Information))
        {
            this._logger.LogInformation("Connecting to toolbox '{ToolboxName}' at {ProxyUrl}.", toolboxName, proxyUrl);
        }

        var handler = new FoundryToolboxBearerTokenHandler(this._credential, this._featuresHeader)
        {
            InnerHandler = new HttpClientHandler()
        };

        var httpClient = new HttpClient(handler);

        var transportOptions = new HttpClientTransportOptions
        {
            Endpoint = new Uri(proxyUrl),
            Name = toolboxName,
        };

        var transport = new HttpClientTransport(transportOptions, httpClient);

        var clientOptions = new McpClientOptions
        {
            ClientInfo = new()
            {
                Name = this._agentName,
                Version = this._agentVersion
            }
        };

        var client = await McpClient.CreateAsync(
            transport,
            clientOptions,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        var mcpTools = await client.ListToolsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);

        if (this._logger.IsEnabled(LogLevel.Information))
        {
            this._logger.LogInformation(
                "Toolbox '{ToolboxName}': discovered {ToolCount} tool(s).",
                toolboxName,
                mcpTools.Count);
        }

        var wrapped = new List<AITool>(mcpTools.Count);
        foreach (var tool in mcpTools)
        {
            wrapped.Add(new ConsentAwareMcpClientAIFunction(tool, toolboxName));
        }

        _ = version; // reserved for future version-specific routing; currently handled server-side by the proxy.

        return new CachedToolbox(client, httpClient, wrapped);
    }

    /// <inheritdoc/>
    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    /// <inheritdoc/>
    public async ValueTask DisposeAsync()
    {
        foreach (var cached in this._toolboxes.Values)
        {
            await cached.Client.DisposeAsync().ConfigureAwait(false);
            cached.HttpClient.Dispose();
        }

        this._toolboxes.Clear();
        this._lazyOpenLock.Dispose();
    }

    private sealed record CachedToolbox(McpClient Client, HttpClient HttpClient, IReadOnlyList<AITool> Tools);
}
