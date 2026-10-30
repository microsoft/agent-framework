// Copyright (c) Microsoft. All rights reserved.

using System;
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
/// Lists skills from an MCP server and provides access to their <c>SKILL.md</c> files and supporting resources.
/// </summary>
/// <remarks>
/// <para>
/// <see cref="GetSkillsAsync"/> requests the available skills through <c>skills/list</c>.
/// The server must declare the <c>io.modelcontextprotocol/skills</c> extension;
/// otherwise, this source returns an empty list without sending a request.
/// Each listed skill includes a name, description, and resource list with expected byte sizes and content hashes.
/// This resource list is called the manifest and includes <c>SKILL.md</c>, which contains the skill's instructions.
/// </para>
/// <para>
/// The skill list may span multiple response pages, each with a time to live (TTL).
/// The list is cached until any page expires, then fetched again on the next <see cref="GetSkillsAsync"/> call.
/// A missing, zero, or negative page TTL causes the list to be fetched on every call.
/// Disable other caches around this source, including the builder's cache through
/// <see cref="AgentSkillsProviderBuilder.DisableCaching"/>, so this source can check expiration on each call.
/// </para>
/// <para>
/// Listing a skill does not fetch its files. The returned skill object fetches <c>SKILL.md</c>
/// and supporting resources only when their content is requested. Only resources in its manifest are available.
/// Each resource response must contain one text or binary content block; <c>SKILL.md</c> must contain text.
/// Fetched content is checked against the resource's expected size and content hash.
/// The name and description at the start of <c>SKILL.md</c> must also match the listed skill.
/// </para>
/// <para>
/// Each skill object caches resource content separately from the skill list, using each resource response's TTL.
/// Expired resource content is fetched again on access. A missing, zero, or negative resource TTL
/// causes content to be fetched on every access. All TTLs start when responses arrive, before validation.
/// </para>
/// <para>
/// If fetched resource content has a different size or content hash than its manifest entry,
/// the skill that owns that resource is queued for refresh.
/// The resource read returns previously verified cached content if available and caches it indefinitely for that skill object;
/// otherwise, it throws. Other resource-read and validation errors propagate without queuing a skill refresh.
/// </para>
/// <para>
/// On the next <see cref="GetSkillsAsync"/> call, <c>skills/get</c> fetches updated metadata and resource lists
/// for queued skills. Skills that no longer exist on the server are removed from the cached list.
/// If the cached skill list has expired, <c>skills/list</c> fetches the whole list instead.
/// Each successful <c>skills/get</c> response controls only that skill's lifetime, not the list's lifetime.
/// When the skill expires, the next <see cref="GetSkillsAsync"/> call refreshes it through <c>skills/get</c>.
/// A failed refresh leaves the previous list unchanged and is retried on a later call.
/// </para>
/// <para>
/// Refreshes return a new list with new objects for updated skills. Previously returned skill objects
/// continue using the resource URIs, sizes, and content hashes they were created with.
/// Previously returned content stays unchanged. Callers must load the new skill object to use an update.
/// Refreshes happen only on request, not in the background.
/// </para>
/// <para>
/// <see cref="AgentMcpSkillsSourceOptions"/> limits listing pages, skill counts, and resource sizes.
/// Invalid pages, repeated cursors, and exceeded limits fail the request rather than returning a partial list.
/// These limits do not bound incoming message size or total memory use. Configure input-size limits
/// in the MCP client, transport, or host as needed.
/// </para>
/// <para>
/// Supporting-resource names must stay within the skill's directory.
/// Resource URIs are sent to the connected MCP server, not opened locally.
/// These checks do not replace server-side authorization.
/// </para>
/// <para>
/// The caller owns the MCP client. Disposing this source does not dispose the client;
/// previously returned skills can continue reading resources while that client remains usable.
/// </para>
/// <para>
/// <strong>Security:</strong> Remote skills are loaded only when this source is explicitly configured.
/// Only connect to servers you trust and treat their content as untrusted input.
/// Malicious instructions or scripts can manipulate the agent or expose data.
/// A matching content hash does not prove that content is safe: the server supplies both the hash and the content.
/// </para>
/// </remarks>
public sealed partial class AgentMcpSkillsSource : AgentSkillsSource
{
    private const string SkillsExtensionName = "io.modelcontextprotocol/skills";

    [SuppressMessage("Usage", "CA2213:Disposable fields should be disposed", Justification = "The MCP client is supplied and owned by the caller, who is responsible for disposing it.")]
    private readonly McpClient _client;
    private readonly ILogger _logger;
    private readonly McpSkillsCatalog _catalog;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentMcpSkillsSource"/> class.
    /// </summary>
    /// <param name="client">An MCP client connected to a server that supports <c>skills/list</c>. The caller retains ownership of the client and is responsible for disposing it.</param>
    /// <param name="options">Optional limits for listing pages, skill counts, and resource sizes.</param>
    /// <param name="loggerFactory">Optional factory for diagnostic logging.</param>
    /// <exception cref="ArgumentNullException"><paramref name="client"/> is <see langword="null"/>.</exception>
    /// <exception cref="ArgumentOutOfRangeException">A configured limit is not positive.</exception>
    public AgentMcpSkillsSource(McpClient client, AgentMcpSkillsSourceOptions? options = null, ILoggerFactory? loggerFactory = null)
        : this(client, options, loggerFactory, TimeProvider.System)
    {
    }

    internal AgentMcpSkillsSource(McpClient client, AgentMcpSkillsSourceOptions? options, ILoggerFactory? loggerFactory, TimeProvider timeProvider)
    {
        this._client = Throw.IfNull(client);
        loggerFactory ??= NullLoggerFactory.Instance;
        this._logger = loggerFactory.CreateLogger<AgentMcpSkillsSource>();
        this._catalog = new McpSkillsCatalog(this._client, options, this._logger, Throw.IfNull(timeProvider));
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

        IList<AgentSkill> skills = await this._catalog.GetSkillsAsync(cancellationToken).ConfigureAwait(false);

        LogSkillsLoadedTotal(this._logger, skills.Count);

        return skills;
    }

    /// <inheritdoc/>
    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            this._catalog.Dispose();
        }

        base.Dispose(disposing);
    }

    /// <summary>
    /// Logs that the server does not declare support for skills.
    /// </summary>
    [LoggerMessage(LogLevel.Debug, "No io.modelcontextprotocol/skills extension declared by MCP server; skill discovery is skipped.")]
    private static partial void LogSkillsExtensionAbsent(ILogger logger);

    /// <summary>
    /// Reports how many skills the source returned.
    /// </summary>
    [LoggerMessage(LogLevel.Information, "Successfully loaded {Count} skills from MCP server")]
    private static partial void LogSkillsLoadedTotal(ILogger logger, int count);
}
