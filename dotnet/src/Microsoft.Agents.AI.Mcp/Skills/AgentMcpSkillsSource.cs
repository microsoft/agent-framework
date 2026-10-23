// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol.Client;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AgentSkillsSource"/> that discovers Agent Skills served over the Model Context Protocol (MCP).
/// </summary>
/// <remarks>
/// <para>
/// Uses <c>skills/list</c> when the server declares the <c>io.modelcontextprotocol/skills</c> extension.
/// Returns an empty skill list without sending a discovery request when the extension is not declared.
/// </para>
/// <para>
/// Listed skill discovery is based on the Skills extension specification incorporating the
/// working group's decision dated <c>2026-09-08</c>.
/// Support currently includes skill discovery through <c>skills/list</c> and reading listed skill resources,
/// but not the full extension.
/// </para>
/// <para>
/// Listed skills provide a name, description, and list of resources. Instructions and supporting resources
/// are fetched from the MCP server when requested. Only supporting resources listed by the server are available.
/// Each listed resource read must return exactly one text or binary content block; <c>SKILL.md</c> must contain text.
/// Page counts, total skill counts, and individual resource sizes
/// are bounded by <see cref="AgentMcpSkillsSourceOptions"/>. Discovery follows continuation cursors
/// until exhausted and fails on repeated cursors, invalid pages, or exceeded limits instead of returning a partial catalog.
/// These checks do not limit incoming messages before the supplied client receives and parses them.
/// </para>
/// <para>
/// Skills discovered through <c>skills/list</c> are cached according to server-provided TTLs.
/// When any page expires, the skills are refreshed on the next request.
/// If any page has no TTL, the skill list is requested from the server on every call.
/// To honor these TTLs, disable any additional caching layers around this source,
/// including the builder's cache by calling <see cref="AgentSkillsProviderBuilder.DisableCaching"/>.
/// </para>
/// <para>
/// Supporting resource names are checked for absolute paths, parent traversal (including
/// percent-encoded forms), and control characters before an MCP request is sent. Resource URIs
/// retain their MCP resource schemes: they are sent to the connected server, not opened locally.
/// This client-side guard does not replace server-side authorization.
/// </para>
/// <para>
/// <strong>Security considerations:</strong> This source discovers and loads skills — including full
/// skill instructions and supporting resources — from a
/// remote MCP server that the caller connects to explicitly (via <c>UseMcpSkills</c>); it is never
/// enabled by default. A compromised, malicious, or simply untrustworthy MCP server can return
/// adversarial skill content designed to manipulate the agent through indirect prompt injection, or
/// instructions/scripts designed to exfiltrate data once loaded and, for script-capable skills,
/// executed. Only connect this source to MCP servers you trust, and review discovery and resource limits (<see cref="AgentMcpSkillsSourceOptions"/>)
/// to bound the impact of a malicious server. A matching digest proves consistency with the resource manifest,
/// not trustworthiness: a server controlling both the manifest and resource can replace both.
/// </para>
/// <para>
/// This source does not impose a byte limit on individual or combined <c>skills/list</c> responses.
/// Page-count, skill-count, and resource-size limits do not bound incoming message size or total
/// memory consumption. A malicious, compromised, or misconfigured server can return oversized
/// responses that cause excessive memory consumption. Application developers are responsible for
/// configuring appropriate input-size and resource limits through their chosen MCP client, transport,
/// or hosting environment.
/// </para>
/// </remarks>
public sealed partial class AgentMcpSkillsSource : AgentSkillsSource
{
    private const string SkillsExtensionName = "io.modelcontextprotocol/skills";

    [SuppressMessage("Usage", "CA2213:Disposable fields should be disposed", Justification = "The MCP client is supplied and owned by the caller, who is responsible for disposing it.")]
    private readonly McpClient _client;
    private readonly ILogger _logger;
    private readonly McpSkillsLoader _skillsLoader;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentMcpSkillsSource"/> class.
    /// </summary>
    /// <param name="client">An MCP client connected to a server that supports <c>skills/list</c>. The caller retains ownership of the client and is responsible for disposing it.</param>
    /// <param name="options">Optional options that control skill loading.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public AgentMcpSkillsSource(McpClient client, AgentMcpSkillsSourceOptions? options = null, ILoggerFactory? loggerFactory = null)
    {
        this._client = Throw.IfNull(client);
        loggerFactory ??= NullLoggerFactory.Instance;
        this._logger = loggerFactory.CreateLogger<AgentMcpSkillsSource>();
        this._skillsLoader = new McpSkillsLoader(this._client, this._logger, options);
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
    {
#pragma warning disable MAAI001
        FeatureUsage.MarkUsed((int)Mcp.FeatureIndex.CoreMcpSkillsSource);
#pragma warning restore MAAI001

        cancellationToken.ThrowIfCancellationRequested();

        if (this._client.ServerCapabilities.Extensions?.ContainsKey(SkillsExtensionName) != true)
        {
            LogSkillsExtensionAbsent(this._logger);
            return [];
        }

        IList<AgentSkill> skills = await this._skillsLoader.DiscoverAsync(cancellationToken).ConfigureAwait(false);

        LogSkillsLoadedTotal(this._logger, skills.Count);

        return skills;
    }

    /// <inheritdoc/>
    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            this._skillsLoader.Dispose();
        }

        base.Dispose(disposing);
    }

    [LoggerMessage(LogLevel.Information, "Successfully loaded {Count} skills from MCP server")]
    private static partial void LogSkillsLoadedTotal(ILogger logger, int count);

    [LoggerMessage(LogLevel.Debug, "No io.modelcontextprotocol/skills extension declared by MCP server; skill discovery is skipped.")]
    private static partial void LogSkillsExtensionAbsent(ILogger logger);
}
