// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Azure.Core;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI.Foundry.Hosting;
#pragma warning disable SYSLIB1006 // Preserve the legacy EventId 0 for every migrated log message.

/// <summary>
/// An <see cref="IHostedService"/> that resolves the Foundry Toolboxes MCP proxy configuration at container
/// startup and opens the configured toolboxes for each response.
/// </summary>
/// <remarks>
/// <para>
/// The toolbox proxy base URL is derived from the platform-injected
/// <c>FOUNDRY_PROJECT_ENDPOINT</c> environment variable per <c>tools-integration-spec.md</c>
/// §2–§3. The per-toolbox proxy URL is constructed as
/// <c>{FOUNDRY_PROJECT_ENDPOINT}/toolboxes/{toolboxName}/mcp?api-version=v1</c>.
/// </para>
/// <para>
/// The endpoint can also come from a configured override or, as a local-development fallback,
/// <c>AZURE_AI_PROJECT_ENDPOINT</c>. If no endpoint is resolved, startup completes with
/// toolbox support disabled and the toolbox health check reports <c>Healthy</c>.
/// </para>
/// <para>
/// The proxy identifies the caller only by the platform per-request call id
/// (<c>x-agent-foundry-call-id</c>); the user id is never forwarded. An MCP session therefore belongs to the
/// call id that opened it. Startup performs no network I/O. Each response opens its own MCP session per
/// toolbox through a <see cref="ToolboxRequestScope"/>, discovers the tools available to its caller, and ends
/// every session when the response completes. No MCP session is shared between responses.
/// </para>
/// <para>
/// The call id is fixed on each connection when it is created and sent on every request of its MCP session,
/// including tool calls made after the response's execution context is gone. It is never read from ambient state.
/// </para>
/// <para>
/// Discovered tools with <c>_meta.tool_configuration.require_approval</c> set to <c>always</c>
/// require approval for each call through <see cref="ApprovalRequiredAIFunction"/>. An explicit
/// unsupported or malformed configuration also requires approval and is logged as a warning.
/// Existing approval requirements exposed by the function's services take precedence over metadata.
/// Tools with no approval configuration, or with <c>require_approval</c> set to <c>never</c>,
/// retain their normal invocation behavior.
/// </para>
/// </remarks>
internal sealed partial class FoundryToolboxService : IHostedService, IAsyncDisposable
{
    private const string FailedOpenOwner = "failed toolbox open";
    private const string ResponseScopeOwner = "response scope";

    private readonly FoundryToolboxServiceOptions _options;
    private readonly TokenCredential _credential;
    private readonly ILogger<FoundryToolboxService> _logger;

    private string? _resolvedEndpoint;
    private string? _featuresHeader;
    private HttpMessageHandler? _primaryHandler;
    private string _agentName = "hosted-agent";
    private string _agentVersion = "1.0.0";

    /// <summary>
    /// Gets the consent link policy built from <see cref="FoundryToolboxServiceOptions.AllowedOAuthConsentOrigins"/>.
    /// The response handler applies it before surfacing any consent link from these toolboxes.
    /// </summary>
    internal OAuthConsentLinkPolicy ConsentLinkPolicy { get; }

    /// <summary>
    /// Gets the startup status of the service. Remains <see cref="FoundryToolboxStartupStatus.Pending"/>
    /// until <see cref="StartAsync"/> completes.
    /// </summary>
    /// <remarks>
    /// The toolbox health check reports its registration's failure status while startup is pending
    /// (<c>Unhealthy</c> by default). Normal startup completes with <see cref="FoundryToolboxStartupStatus.Healthy"/>
    /// or <see cref="FoundryToolboxStartupStatus.NoEndpoint"/>, both of which report <c>Healthy</c>. A healthy check
    /// does not mean a toolbox is reachable: toolboxes are opened only for responses.
    /// </remarks>
    public FoundryToolboxStartupStatus StartupStatus { get; private set; } = FoundryToolboxStartupStatus.Pending;

    /// <summary>
    /// Gets the distinct toolbox names each response opens, in configured order. Empty until startup
    /// completes, and when no project endpoint is resolved.
    /// </summary>
    public IReadOnlyList<string> ToolboxNames { get; private set; } = [];

    /// <summary>
    /// Initializes a new instance of <see cref="FoundryToolboxService"/>.
    /// </summary>
    public FoundryToolboxService(
        FoundryToolboxServiceOptions options,
        TokenCredential credential,
        ILogger<FoundryToolboxService>? logger = null)
    {
        ArgumentNullException.ThrowIfNull(options);
        ArgumentNullException.ThrowIfNull(credential);

        this._options = options;
        this._credential = credential;
        this._logger = logger ?? NullLogger<FoundryToolboxService>.Instance;
        this.ConsentLinkPolicy = new OAuthConsentLinkPolicy(this._options.AllowedOAuthConsentOrigins);
    }

    /// <summary>
    /// Test-only seam for the network-doing toolbox-open step. When set, <see cref="OpenToolboxAsync"/>
    /// delegates to this instead of connecting to the live MCP proxy, so request-scope resolution and
    /// cleanup can be unit-tested deterministically. It receives the toolbox name and the response's
    /// platform call id. Never set in production.
    /// </summary>
    internal Func<string, string?, CancellationToken, Task<ToolboxOpenResult>>? ToolboxOpener { get; set; }

    /// <summary>
    /// Test-only seam that supplies the primary HTTP handler shared by every toolbox connection.
    /// Never set in production, where <see cref="CreateToolboxPrimaryHttpMessageHandler"/> is used.
    /// </summary>
    internal Func<HttpMessageHandler>? PrimaryHttpMessageHandlerFactory { get; set; }

    /// <summary>
    /// Resolves the proxy endpoint and validates the configured toolbox names. No connection is opened.
    /// </summary>
    /// <param name="cancellationToken">Not used; startup performs no I/O.</param>
    /// <returns>A completed task.</returns>
    /// <exception cref="InvalidOperationException">
    /// A configured toolbox name would not resolve to a single, intact path segment of the proxy URL.
    /// </exception>
    public Task StartAsync(CancellationToken cancellationToken)
    {
        // Per tools-integration-spec.md §2-§3, the container derives the toolbox proxy base
        // URL from the platform-injected FOUNDRY_PROJECT_ENDPOINT. The EndpointOverride
        // option exists for tests; AZURE_AI_PROJECT_ENDPOINT is honored as a local-dev
        // fallback to mirror the convention used by AF-repo samples.
        var projectEndpoint = this._options.EndpointOverride
            ?? Environment.GetEnvironmentVariable("FOUNDRY_PROJECT_ENDPOINT")
            ?? Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT");

        if (string.IsNullOrEmpty(projectEndpoint))
        {
            LogToolboxSupportDisabled(this._logger);
            this.StartupStatus = FoundryToolboxStartupStatus.NoEndpoint;
            return Task.CompletedTask;
        }

        this._resolvedEndpoint = projectEndpoint.TrimEnd('/');
        this._featuresHeader = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_TOOLSET_FEATURES");
        this._agentName = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_NAME") ?? "hosted-agent";
        this._agentVersion = Environment.GetEnvironmentVariable("FOUNDRY_AGENT_VERSION") ?? "1.0.0";

        // A name that would move the request target is a configuration error. Reject it before the
        // container serves traffic instead of retrying it, and failing, on every response.
        var names = new List<string>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var toolboxName in this._options.ToolboxNames)
        {
            if (seen.Add(toolboxName))
            {
                this.EnsureSafeToolboxName(toolboxName);
                names.Add(toolboxName);
            }
        }

        if (names.Count == 0)
        {
            LogNoPreRegisteredToolboxes(this._logger);
        }
        else
        {
            // One connection pool serves every toolbox connection. Each response still opens its own
            // MCP session over it, so pooled sockets carry no caller identity between responses.
            this._primaryHandler = this.PrimaryHttpMessageHandlerFactory?.Invoke()
                ?? CreateToolboxPrimaryHttpMessageHandler();
            LogToolboxesConfigured(this._logger, names.Count);
        }

        this.ToolboxNames = names;
        this.StartupStatus = FoundryToolboxStartupStatus.Healthy;
        return Task.CompletedTask;
    }

    /// <summary>
    /// Creates the owner of the toolbox connections opened while handling one response.
    /// </summary>
    /// <param name="callId">
    /// The response's platform call id (<c>x-agent-foundry-call-id</c>), or <see langword="null"/> when the platform
    /// supplied none. Every connection the scope opens sends it.
    /// </param>
    internal ToolboxRequestScope CreateRequestScope(string? callId) => new(this, callId);

    /// <summary>
    /// Validates that <paramref name="toolboxName"/> resolves to a single, intact path segment in the
    /// toolbox proxy request URL, so a configured name cannot change the request target.
    /// </summary>
    /// <remarks>
    /// Rather than block-listing characters, this builds the proxy URL exactly as
    /// <see cref="OpenToolboxAsync"/> does and confirms, via <see cref="Uri"/>, that the name lands as
    /// one path segment between <c>toolboxes</c> and <c>mcp</c> and alters nothing else: the scheme and
    /// authority still match the configured endpoint, no fragment is introduced, the path is still
    /// <c>{base}/toolboxes/{name}/mcp</c>, and that single segment round-trips back to the original
    /// name. This is deliberately forgiving — any character that stays inside the segment (for example
    /// <c>:</c>, <c>@</c>, <c>~</c>, or a dot that is not a standalone <c>.</c>/<c>..</c>) is allowed —
    /// while a name that would move the target is rejected: path separators (<c>/</c>, <c>\</c>),
    /// <c>.</c>/<c>..</c> traversal, a <c>?</c>/<c>#</c> that ends the path early, and their
    /// percent-encoded forms (an encoded separator does not round-trip, so it is rejected before a
    /// downstream proxy could decode it).
    /// </remarks>
    /// <param name="toolboxName">The toolbox name to validate.</param>
    /// <exception cref="InvalidOperationException">
    /// Thrown when the name would not resolve to a single, intact path segment.
    /// </exception>
    private void EnsureSafeToolboxName(string toolboxName)
    {
        // No endpoint resolved yet means there is no URL to protect; the caller surfaces the
        // missing-endpoint error separately, so skip the effect-based check here.
        if (string.IsNullOrEmpty(this._resolvedEndpoint))
        {
            return;
        }

        var baseUri = new Uri(this._resolvedEndpoint, UriKind.Absolute);
        var candidate = $"{this._resolvedEndpoint}/toolboxes/{toolboxName}/mcp?api-version={FoundryToolboxServiceOptions.ApiVersion}";

        if (Uri.TryCreate(candidate, UriKind.Absolute, out var uri)
            && string.Equals(uri.Scheme, baseUri.Scheme, StringComparison.Ordinal)
            && string.Equals(uri.Authority, baseUri.Authority, StringComparison.Ordinal)
            && string.IsNullOrEmpty(uri.Fragment))
        {
            var prefix = $"{baseUri.AbsolutePath.TrimEnd('/')}/toolboxes/";
            const string Suffix = "/mcp";
            var path = uri.AbsolutePath;

            if (path.Length > prefix.Length + Suffix.Length
                && path.StartsWith(prefix, StringComparison.Ordinal)
                && path.EndsWith(Suffix, StringComparison.Ordinal))
            {
                var segment = path.Substring(prefix.Length, path.Length - prefix.Length - Suffix.Length);
                if (segment.Length > 0
                    && segment.IndexOf('/') < 0
                    && string.Equals(Uri.UnescapeDataString(segment), toolboxName, StringComparison.Ordinal))
                {
                    return;
                }
            }
        }

        throw new InvalidOperationException(
            $"Toolbox name '{toolboxName}' is not a valid single-segment identifier. " +
            "Toolbox names must resolve to a single path segment and must not alter the request target.");
    }

    internal static HttpClientHandler CreateToolboxPrimaryHttpMessageHandler() =>
        new()
        {
            UseCookies = false,
            AllowAutoRedirect = false,
            CheckCertificateRevocationList = true
        };

    internal static HttpMessageHandler CreateToolboxHttpMessageHandler(
        Uri endpoint,
        TokenCredential credential,
        string tokenScope,
        string? featuresHeader,
        HttpMessageHandler? primaryHandler = null,
        string? callId = null)
    {
        _ = Throw.IfNull(endpoint);
        _ = Throw.IfNull(credential);
        _ = Throw.IfNullOrWhitespace(tokenScope);

        primaryHandler ??= CreateToolboxPrimaryHttpMessageHandler();
        var originPinningHandler = new OriginPinningHandler(endpoint)
        {
            InnerHandler = primaryHandler
        };

        // The bearer handler must run before the pinning handler so any credential it adds
        // is removed before network dispatch if a future transport creates a foreign request.
        return new FoundryToolboxBearerTokenHandler(credential, tokenScope, featuresHeader, endpoint, callId)
        {
            InnerHandler = originPinningHandler
        };
    }

    internal static HttpClientTransportOptions CreateToolboxTransportOptions(Uri endpoint, string toolboxName) =>
        new()
        {
            Endpoint = endpoint,
            Name = toolboxName,
            // Streamable HTTP does not accept the server-selected message endpoint used by
            // the legacy SSE transport, so requests remain bound to the configured origin.
            TransportMode = HttpTransportMode.StreamableHttp,

            // A connection lives for one response and its tools are discovered again by the next one, so
            // unsolicited server messages such as list-changed notifications have no use. Messages that belong
            // to a request still arrive on that request's own response stream.
            EnableStandaloneGetStream = false,

            // End the MCP session on the server when the response's connection is disposed.
            OwnsSession = true,
        };

    /// <summary>
    /// Opens one toolbox for the current response and discovers its tools, or reports the OAuth consent
    /// the caller must complete before its tools can be discovered.
    /// </summary>
    private async Task<ToolboxOpenResult> OpenToolboxAsync(
        string toolboxName,
        string? callId,
        CancellationToken cancellationToken)
    {
        // Defense-in-depth: names are validated at startup, and this is the single point where a
        // name is used to build the request URL, so it is validated again independent of the caller.
        this.EnsureSafeToolboxName(toolboxName);

        // Test seam: when set, the open behavior (the only part that does real network I/O via the
        // MCP transport) is supplied by the test so the resolution logic can be exercised without a
        // live toolbox proxy. Never set in production.
        if (this.ToolboxOpener is { } opener)
        {
            return await opener(toolboxName, callId, cancellationToken).ConfigureAwait(false);
        }

        var proxyUrl = $"{this._resolvedEndpoint!}/toolboxes/{toolboxName}/mcp?api-version={FoundryToolboxServiceOptions.ApiVersion}";

        LogConnectingToToolbox(this._logger, toolboxName, proxyUrl);

        // Build the endpoint URI before allocating the HttpClient so a malformed URL cannot leak it.
        var endpoint = new Uri(proxyUrl);
        var primaryHandler = Volatile.Read(ref this._primaryHandler)
            ?? throw new ObjectDisposedException(nameof(FoundryToolboxService));

        // The connection's own handlers wrap the shared primary handler without owning it, so disposing
        // this connection's HttpClient leaves the pool to the service. Its bearer handler carries the
        // response's call id, binding the MCP session opened below to that caller.
        var httpClient = new HttpClient(
            CreateToolboxHttpMessageHandler(
                endpoint,
                this._credential,
                this._options.TokenScope,
                this._featuresHeader,
                new SharedHttpMessageHandler(primaryHandler),
                callId));

        var transportOptions = CreateToolboxTransportOptions(endpoint, toolboxName);
        var transport = new HttpClientTransport(transportOptions, httpClient);

        var clientOptions = new McpClientOptions
        {
            ClientInfo = new()
            {
                Name = this._agentName,
                Version = this._agentVersion
            }
        };

        // McpClient.CreateAsync performs the Streamable HTTP initialize handshake (the transport is
        // pinned, so there is no fallback to another transport) and can throw for an unreachable
        // proxy. Keep it inside the try so the HttpClient is always disposed on failure.
        McpClient? client = null;
        IList<McpClientTool> mcpTools;
        try
        {
            client = await McpClient.CreateAsync(
                transport,
                clientOptions,
                cancellationToken: cancellationToken).ConfigureAwait(false);

            mcpTools = await client.ListToolsAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (McpProtocolException ex) when (
            ToolboxConsentParser.TryParseConsentRequired(toolboxName, ex.Message, out var consents))
        {
            // A tool source needs this caller's OAuth consent before it can be enumerated. Release the
            // half-open connection and report the consent; a disposal failure must not replace it.
            await this.DisposeConnectionAsync(toolboxName, new(client, httpClient, []), FailedOpenOwner).ConfigureAwait(false);
            return new ToolboxOpenResult(Connection: null, Consents: consents);
        }
        catch
        {
            // A disposal failure must not replace the original open failure.
            await this.DisposeConnectionAsync(toolboxName, new(client, httpClient, []), FailedOpenOwner).ConfigureAwait(false);
            throw;
        }

        LogToolboxToolsDiscovered(this._logger, toolboxName, mcpTools.Count);

        var wrapped = new List<AITool>(mcpTools.Count);
        foreach (var tool in mcpTools)
        {
            AIFunction function = new ConsentAwareMcpClientAIFunction(tool, toolboxName);
            wrapped.Add(this.RequiresToolApproval(tool, toolboxName)
                ? new ApprovalRequiredAIFunction(function)
                : function);
        }

        return new ToolboxOpenResult(new ToolboxConnection(client!, httpClient, wrapped), Consents: null);
    }

    internal bool RequiresToolApproval(AIFunction tool, string toolboxName)
    {
        if (tool.GetService<ApprovalRequiredAIFunction>() is not null)
        {
            return true;
        }

        if (tool.GetService<McpClientTool>()?.ProtocolTool.Meta is not { } meta
            || !meta.TryGetPropertyValue("tool_configuration", out var configuration))
        {
            return false;
        }

        if (configuration is JsonObject toolConfiguration)
        {
            if (!toolConfiguration.TryGetPropertyValue("require_approval", out var approval))
            {
                return false;
            }

            if (approval is JsonValue value && value.TryGetValue<string>(out var policy))
            {
                if (string.Equals(policy, "always", StringComparison.Ordinal))
                {
                    return true;
                }

                if (string.Equals(policy, "never", StringComparison.Ordinal))
                {
                    return false;
                }
            }
        }

        LogUnsupportedToolApprovalConfiguration(this._logger, tool.Name, toolboxName);
        return true;
    }

    /// <summary>
    /// Disposes the MCP client, then always the HTTP client, logging rather than throwing any failure.
    /// </summary>
    private async Task DisposeConnectionAsync(string toolboxName, ToolboxConnection connection, string owner)
    {
        try
        {
            if (connection.Client is { } client)
            {
                await client.DisposeAsync().ConfigureAwait(false);
            }
        }
        catch (Exception ex)
        {
            LogToolboxResourceDisposalFailed(this._logger, "MCP client", toolboxName, owner, ex);
        }
        finally
        {
            try
            {
                connection.HttpClient.Dispose();
            }
            catch (Exception ex)
            {
                LogToolboxResourceDisposalFailed(this._logger, "HTTP client", toolboxName, owner, ex);
            }
        }
    }

    /// <inheritdoc/>
    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    /// <summary>
    /// Releases the primary HTTP handler shared by toolbox connections. Toolbox connections themselves belong to
    /// the response scope that opened them.
    /// </summary>
    public ValueTask DisposeAsync()
    {
        Interlocked.Exchange(ref this._primaryHandler, null)?.Dispose();
        return default;
    }

    /// <summary>
    /// Forwards requests to a shared handler without taking ownership of it, so disposing a connection's
    /// <see cref="HttpClient"/> does not dispose the service's connection pool.
    /// </summary>
    private sealed class SharedHttpMessageHandler : HttpMessageHandler
    {
        private readonly HttpMessageInvoker _invoker;

        internal SharedHttpMessageHandler(HttpMessageHandler sharedHandler)
        {
            this._invoker = new HttpMessageInvoker(sharedHandler, disposeHandler: false);
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            this._invoker.SendAsync(request, cancellationToken);

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                this._invoker.Dispose();
            }

            base.Dispose(disposing);
        }
    }

    /// <summary>
    /// Owns the toolbox connections opened for one response and ends them when the response completes.
    /// </summary>
    /// <remarks>
    /// A scope is created for one response and used only by it. <see cref="ResolveAsync"/> opens every configured
    /// toolbox concurrently with the response's call id; <see cref="DisposeAsync"/> ends every connection the scope
    /// opened. No connection is shared with, or reused by, another response.
    /// </remarks>
    internal sealed class ToolboxRequestScope : IAsyncDisposable
    {
        private readonly FoundryToolboxService? _owner;
        private readonly string? _callId;
        private readonly List<(string ToolboxName, ToolboxConnection Connection)> _connections = [];
        private bool _disposed;

        internal ToolboxRequestScope(FoundryToolboxService? owner, string? callId)
        {
            this._owner = owner;
            this._callId = callId;
        }

        /// <summary>Creates a scope with no toolboxes, for a handler that has no toolbox service.</summary>
        internal static ToolboxRequestScope CreateInactive() => new(owner: null, callId: null);

        /// <summary>
        /// Opens every configured toolbox for this response and returns the tools to add, or the OAuth consents
        /// the caller must complete first.
        /// </summary>
        /// <remarks>
        /// A toolbox that cannot be opened for a reason other than cancellation of
        /// <paramref name="cancellationToken"/> is logged and skipped, so the response continues without its
        /// tools. Every opened connection is owned by this scope before this method returns, including when
        /// another toolbox's open is canceled.
        /// </remarks>
        /// <param name="cancellationToken">The response cancellation token.</param>
        /// <returns>The tools to add, or the consents that stop the turn.</returns>
        /// <exception cref="OperationCanceledException"><paramref name="cancellationToken"/> was canceled.</exception>
        internal async ValueTask<ToolboxRequestResolution> ResolveAsync(CancellationToken cancellationToken)
        {
            if (this._owner is not { } owner || owner.ToolboxNames.Count == 0)
            {
                return ToolboxRequestResolution.Empty;
            }

            var outcomes = await Task.WhenAll(
                owner.ToolboxNames.Select(toolboxName => this.OpenAsync(owner, toolboxName, cancellationToken)))
                .ConfigureAwait(false);

            List<AITool> tools = [];
            List<McpConsentInfo> consents = [];
            foreach (var outcome in outcomes)
            {
                tools.AddRange(outcome.Tools);
                consents.AddRange(outcome.Consents);
            }

            return consents.Count > 0
                ? new ToolboxRequestResolution(Tools: [], Consents: consents)
                : new ToolboxRequestResolution(Tools: tools, Consents: []);
        }

        /// <summary>Ends every connection this scope opened. Failures are logged, never thrown.</summary>
        public async ValueTask DisposeAsync()
        {
            (string ToolboxName, ToolboxConnection Connection)[] connections;
            lock (this._connections)
            {
                if (this._disposed)
                {
                    return;
                }

                this._disposed = true;
                connections = [.. this._connections];
                this._connections.Clear();
            }

            if (this._owner is { } owner)
            {
                await Task.WhenAll(connections.Select(
                    entry => owner.DisposeConnectionAsync(entry.ToolboxName, entry.Connection, ResponseScopeOwner)))
                    .ConfigureAwait(false);
            }
        }

        private async Task<ToolboxOpenOutcome> OpenAsync(
            FoundryToolboxService owner,
            string toolboxName,
            CancellationToken cancellationToken)
        {
            try
            {
                var result = await owner.OpenToolboxAsync(toolboxName, this._callId, cancellationToken).ConfigureAwait(false);
                if (result.Connection is not { } connection)
                {
                    return new ToolboxOpenOutcome(Tools: [], Consents: result.Consents ?? []);
                }

                await this.AdoptAsync(owner, toolboxName, connection).ConfigureAwait(false);
                return new ToolboxOpenOutcome(Tools: connection.Tools, Consents: []);
            }
            catch (Exception ex) when (ex is not OperationCanceledException || !cancellationToken.IsCancellationRequested)
            {
                // An unreachable proxy, a timeout, or any other failure that is not this response's own
                // cancellation removes only this toolbox from the response.
                LogToolboxUnavailableForResponse(owner._logger, toolboxName, ex);
                return new ToolboxOpenOutcome(Tools: [], Consents: []);
            }
        }

        private async ValueTask AdoptAsync(FoundryToolboxService owner, string toolboxName, ToolboxConnection connection)
        {
            bool adopted;
            lock (this._connections)
            {
                adopted = !this._disposed;
                if (adopted)
                {
                    this._connections.Add((toolboxName, connection));
                }
            }

            if (!adopted)
            {
                await owner.DisposeConnectionAsync(toolboxName, connection, ResponseScopeOwner).ConfigureAwait(false);
            }
        }

        private readonly record struct ToolboxOpenOutcome(
            IReadOnlyList<AITool> Tools,
            IReadOnlyList<McpConsentInfo> Consents);
    }

    /// <summary>
    /// An open toolbox: its MCP client, the HTTP client that carries the MCP session, and the discovered tools.
    /// </summary>
    internal sealed record ToolboxConnection(IAsyncDisposable? Client, HttpClient HttpClient, IReadOnlyList<AITool> Tools);

    /// <summary>
    /// Outcome of an <see cref="OpenToolboxAsync"/> attempt. Exactly one of the two values is set:
    /// <see cref="Connection"/> when the toolbox opened and its tools were enumerated, or
    /// <see cref="Consents"/> when enumeration is blocked pending user OAuth consent.
    /// </summary>
    internal sealed record ToolboxOpenResult(ToolboxConnection? Connection, IReadOnlyList<McpConsentInfo>? Consents);

    [LoggerMessage(LogLevel.Warning, "Neither FOUNDRY_PROJECT_ENDPOINT nor AZURE_AI_PROJECT_ENDPOINT is set; toolbox support is disabled.", EventId = 0)]
    private static partial void LogToolboxSupportDisabled(ILogger logger);

    [LoggerMessage(LogLevel.Information, "No pre-registered toolbox names configured.", EventId = 0)]
    private static partial void LogNoPreRegisteredToolboxes(ILogger logger);

    [LoggerMessage(LogLevel.Information, "Foundry toolbox support is enabled for {ToolboxCount} toolbox(es). Each response opens its own toolbox connections.", EventId = 0)]
    private static partial void LogToolboxesConfigured(ILogger logger, int toolboxCount);

    [LoggerMessage(LogLevel.Warning, "Toolbox '{ToolboxName}' could not be opened for this response; the response continues without its tools.", EventId = 0)]
    private static partial void LogToolboxUnavailableForResponse(
        ILogger logger,
        string toolboxName,
        Exception exception);

    [LoggerMessage(LogLevel.Warning, "Failed to dispose {Resource} for toolbox {ToolboxName} owned by {Owner}.", EventId = 0)]
    private static partial void LogToolboxResourceDisposalFailed(
        ILogger logger,
        string resource,
        string toolboxName,
        string owner,
        Exception exception);

    [LoggerMessage(LogLevel.Debug, "Connecting to toolbox '{ToolboxName}' at {ProxyUrl}.", EventId = 0)]
    private static partial void LogConnectingToToolbox(
        ILogger logger,
        string toolboxName,
        string proxyUrl);

    [LoggerMessage(LogLevel.Debug, "Toolbox '{ToolboxName}': discovered {ToolCount} tool(s).", EventId = 0)]
    private static partial void LogToolboxToolsDiscovered(
        ILogger logger,
        string toolboxName,
        int toolCount);

    [LoggerMessage(LogLevel.Warning, "Tool '{ToolName}' in toolbox '{ToolboxName}' has an unsupported approval configuration; requiring approval for every call.", EventId = 0)]
    private static partial void LogUnsupportedToolApprovalConfiguration(
        ILogger logger,
        string toolName,
        string toolboxName);
}

/// <summary>
/// The toolbox outcome for one response. A non-empty <see cref="Consents"/> stops the turn for OAuth consent, and
/// <see cref="Tools"/> holds the toolbox tools to add to the run.
/// </summary>
/// <param name="Tools">The toolbox tools to add to the run.</param>
/// <param name="Consents">The OAuth consents the caller must complete before the turn can run.</param>
internal readonly record struct ToolboxRequestResolution(
    IReadOnlyList<AITool> Tools,
    IReadOnlyList<McpConsentInfo> Consents)
{
    /// <summary>Gets the resolution for a response with no toolboxes.</summary>
    internal static ToolboxRequestResolution Empty { get; } = new([], []);
}
