// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
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
/// </remarks>
internal sealed partial class AgentMcpSkillsSource : AgentSkillsSource
{
    /// <summary>
    /// SEP-2640 canonical discovery document URI.
    /// </summary>
    private const string IndexUri = "skill://index.json";

    private readonly McpClient _client;
    private readonly ILogger _logger;
    private readonly Dictionary<string, IMcpSkillEntryLoader> _loaders;
    private readonly TimeSpan? _refreshInterval;

    private IList<AgentSkill>? _cachedSkills;
    private DateTime _lastRefreshedUtc;
    private Task<IList<AgentSkill>>? _refreshTask;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentMcpSkillsSource"/> class.
    /// </summary>
    /// <param name="client">An MCP client connected to a server that exposes Agent Skills resources.</param>
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
        this._refreshInterval = options?.RefreshInterval;
    }

    /// <inheritdoc/>
    public override async Task<IList<AgentSkill>> GetSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken = default)
    {
        if (this.TryGetCachedSkills() is { } cached)
        {
            return cached;
        }

        // Use CAS to ensure only one concurrent refresh runs; other callers await the same task.
        var tcs = new TaskCompletionSource<IList<AgentSkill>>(TaskCreationOptions.RunContinuationsAsynchronously);

        if (Interlocked.CompareExchange(ref this._refreshTask, tcs.Task, null) is { } existing)
        {
            // Wait for the in-flight refresh but let this caller cancel its own wait independently
            // without aborting the shared refresh work.
            // Note: refresh coordination is global — concurrent callers with a different context
            // will observe the refresh owner's context. This is acceptable because AgentMcpSkillsSource
            // does not currently use the context to filter or differentiate skills; all callers receive
            // the same MCP-server-wide skill list.
            return await existing.WaitAsync(cancellationToken).ConfigureAwait(false);
        }

        try
        {
            // The refresh owner uses CancellationToken.None so that a single caller's cancellation
            // does not abort the shared refresh for all concurrent waiters.
            var skills = await this.GetCoreSkillsAsync(context, CancellationToken.None).ConfigureAwait(false);

            this.UpdateCache(skills);

            tcs.SetResult(skills);

            // Allow the current caller to observe cancellation without impacting other awaiters.
            cancellationToken.ThrowIfCancellationRequested();

            return skills;
        }
        catch (Exception ex)
        {
            tcs.TrySetException(ex);
            throw;
        }
        finally
        {
            this._refreshTask = null;
        }
    }

    /// <summary>
    /// Returns the cached skill list if caching is enabled and the cache is still fresh;
    /// otherwise returns <see langword="null"/>.
    /// </summary>
    private IList<AgentSkill>? TryGetCachedSkills()
    {
        if (this._refreshInterval is null || this._cachedSkills is null)
        {
            return null;
        }

        TimeSpan cacheAge = DateTime.UtcNow - this._lastRefreshedUtc;

        if (cacheAge >= this._refreshInterval.Value)
        {
            return null;
        }

        return this._cachedSkills;
    }

    /// <summary>
    /// Stores the skill list and records the refresh timestamp for cache freshness checks.
    /// </summary>
    private void UpdateCache(IList<AgentSkill> skills)
    {
        this._cachedSkills = skills;
        this._lastRefreshedUtc = DateTime.UtcNow;
    }

    /// <summary>
    /// Reads the skill index from the MCP server, dispatches entries to registered loaders, and
    /// returns the aggregated skill list.
    /// </summary>
    private async Task<IList<AgentSkill>> GetCoreSkillsAsync(AgentSkillsSourceContext context, CancellationToken cancellationToken)
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
