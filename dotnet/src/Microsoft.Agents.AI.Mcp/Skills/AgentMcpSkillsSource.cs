// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Shared.Diagnostics;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AgentSkillsSource"/> that discovers Agent Skills served over the Model Context Protocol (MCP).
/// </summary>
/// <remarks>
/// <para>
/// Discovery follows the SEP-2640 recommended approach: the source reads the well-known
/// <c>skill://index.json</c> resource and constructs one <see cref="AgentSkill"/> per index entry.
/// </para>
/// <para>
/// Index entries are dispatched to an <see cref="IMcpSkillEntryLoader"/> by their <c>type</c>:
/// <list type="bullet">
///   <item><description><c>skill-md</c> - handled by <see cref="SkillMdEntryLoader"/>; the skill's
///   <c>SKILL.md</c> and sibling resources are fetched on demand from the MCP server.</description></item>
///   <item><description><c>archive</c> - handled by <see cref="ArchiveEntryLoader"/>; the entry's
///   <c>url</c> points to a single archive resource whose content unpacks into the skill's
///   namespace.</description></item>
/// </list>
/// Entries whose type has no registered loader (e.g. <c>mcp-resource-template</c>) are skipped.
/// </para>
/// <para>
/// If <c>skill://index.json</c> is absent, unreadable, empty, or fails to parse, this source returns an
/// empty list.
/// </para>
/// <para>
/// <b>Thread safety and archive reconciliation.</b> For <c>archive</c>-type skills, every call to
/// <see cref="GetSkillsAsync"/> reconciles a shared on-disk directory: it extracts newly advertised
/// skills, re-extracts existing ones, and prunes those the server no longer advertises. Because that
/// work mutates files (and internal state) that concurrent calls would also touch, running it from
/// multiple threads at once could corrupt the directory or surface partially-extracted skills. To
/// prevent this, the archive reconciliation is guarded by a per-instance lock: only one call performs
/// it at a time, and other concurrent callers wait and then run sequentially.
/// </para>
/// <para>
/// This keeps the directory consistent but means concurrent (and repeated) calls do not share work —
/// each one re-contacts the MCP server and re-reconciles. To avoid that redundant work, place a caching
/// layer in front of this source (for example, via <see cref="AgentSkillsProviderBuilder"/>, which adds
/// one by default):
/// <list type="bullet">
///   <item><description>When the server's skills do not change at runtime, cache with no isolation key
///   (the default <see cref="CachingAgentSkillsSourceOptions.CacheIsolationKeySelector"/>), so a single
///   fetch and reconciliation is shared by all callers for the lifetime of the cache.</description></item>
///   <item><description>When the server's skills can change, additionally set
///   <see cref="CachingAgentSkillsSourceOptions.RefreshInterval"/> so the cache periodically re-fetches
///   and reconciles instead of doing so on every call.</description></item>
/// </list>
/// </para>
/// </remarks>
internal sealed partial class AgentMcpSkillsSource : AgentSkillsSource
{
    /// <summary>
    /// SEP-2640 canonical discovery document URI.
    /// </summary>
    private const string IndexUri = "skill://index.json";

    [SuppressMessage("Usage", "CA2213:Disposable fields should be disposed", Justification = "The MCP client is supplied and owned by the caller, who is responsible for disposing it.")]
    private readonly McpClient _client;
    private readonly ILogger _logger;
    private readonly Dictionary<string, IMcpSkillEntryLoader> _loaders;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentMcpSkillsSource"/> class.
    /// </summary>
    /// <param name="client">An MCP client connected to a server that exposes Agent Skills resources. The caller retains ownership of the client and is responsible for disposing it.</param>
    /// <param name="options">Optional options that control archive-distributed skill handling.</param>
    /// <param name="loggerFactory">Optional logger factory.</param>
    public AgentMcpSkillsSource(McpClient client, AgentMcpSkillsSourceOptions? options = null, ILoggerFactory? loggerFactory = null)
    {
        this._client = Throw.IfNull(client);
        loggerFactory ??= NullLoggerFactory.Instance;
        this._logger = loggerFactory.CreateLogger<AgentMcpSkillsSource>();

        IMcpSkillEntryLoader[] loaders =
        [
            new SkillMdEntryLoader(this._client, loggerFactory),
            new ArchiveEntryLoader(this._client, options, loggerFactory),
        ];

        this._loaders = loaders.ToDictionary(l => l.EntryType, StringComparer.OrdinalIgnoreCase);
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
    {
        McpSkillIndex? index = await this.TryReadIndexAsync(cancellationToken).ConfigureAwait(false);

        // Group entries by type and set aside those a registered loader can handle; entries of any
        // other type are unsupported and logged.
        var entriesByType = new Dictionary<string, List<McpSkillIndexEntry>>(StringComparer.OrdinalIgnoreCase);

        foreach (var group in (index?.Skills ?? []).GroupBy(e => e.Type ?? string.Empty, StringComparer.OrdinalIgnoreCase))
        {
            if (this._loaders.ContainsKey(group.Key))
            {
                entriesByType[group.Key] = group.ToList();
            }
            else
            {
                foreach (var entry in group)
                {
                    LogIndexEntrySkipped(this._logger, entry.Name ?? "(unnamed)", $"unsupported type '{entry.Type ?? "(none)"}'");
                }
            }
        }

        // Invoke every registered loader, even when the server advertises no entries of its type, so
        // each type's lifecycle still runs (e.g. the archive loader prunes leftover directories).
        var skills = new List<AgentSkill>();

        foreach (var loader in this._loaders.Values)
        {
            var entries = entriesByType.TryGetValue(loader.EntryType, out List<McpSkillIndexEntry>? matched) ? matched : [];
            skills.AddRange(await loader.LoadAsync(entries, context, cancellationToken).ConfigureAwait(false));
        }

        LogSkillsLoadedTotal(this._logger, skills.Count);

        return skills;
    }

    /// <inheritdoc/>
    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            foreach (var loader in this._loaders.Values)
            {
                (loader as IDisposable)?.Dispose();
            }
        }

        base.Dispose(disposing);
    }

    private async Task<McpSkillIndex?> TryReadIndexAsync(CancellationToken cancellationToken)
    {
        ReadResourceResult result;

        try
        {
#pragma warning disable CA2234 // Pass system uri objects instead of strings
            result = await this._client.ReadResourceAsync(IndexUri, cancellationToken: cancellationToken).ConfigureAwait(false);
#pragma warning restore CA2234 // Pass system uri objects instead of strings
        }
        catch (McpException ex) when (ex is McpProtocolException pex && pex.ErrorCode == McpErrorCode.ResourceNotFound)
        {
            LogIndexAbsent(this._logger, ex.Message);
            return null;
        }
        catch (McpException ex)
        {
            LogIndexReadFailed(this._logger, ex);
            return null;
        }

        string? indexText = result.Contents.OfType<TextResourceContents>().FirstOrDefault()?.Text;
        if (string.IsNullOrWhiteSpace(indexText))
        {
            LogIndexEmpty(this._logger);
            return null;
        }

        try
        {
            return JsonSerializer.Deserialize(indexText, McpJsonContext.Default.McpSkillIndex);
        }
        catch (JsonException ex)
        {
            LogIndexParseFailed(this._logger, ex);
            return null;
        }
    }

    [LoggerMessage(LogLevel.Information, "Successfully loaded {Count} skills from MCP server")]
    private static partial void LogSkillsLoadedTotal(ILogger logger, int count);

    [LoggerMessage(LogLevel.Debug, "No skill://index.json resource available on MCP server: {Reason}")]
    private static partial void LogIndexAbsent(ILogger logger, string reason);

    [LoggerMessage(LogLevel.Warning, "Failed to read skill://index.json from MCP server.")]
    private static partial void LogIndexReadFailed(ILogger logger, Exception exception);

    [LoggerMessage(LogLevel.Debug, "skill://index.json on MCP server returned empty/non-text contents")]
    private static partial void LogIndexEmpty(ILogger logger);

    [LoggerMessage(LogLevel.Warning, "Failed to parse skill://index.json JSON document.")]
    private static partial void LogIndexParseFailed(ILogger logger, Exception exception);

    [LoggerMessage(LogLevel.Debug, "Skipping skill index entry '{SkillName}': {Reason}")]
    private static partial void LogIndexEntrySkipped(ILogger logger, string skillName, string reason);
}
