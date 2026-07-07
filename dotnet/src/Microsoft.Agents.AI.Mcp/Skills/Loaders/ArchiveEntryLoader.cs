// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using ModelContextProtocol;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI;

/// <summary>
/// Loads <c>archive</c> index entries: each entry's <c>url</c> points to a single archive resource
/// (<c>application/zip</c>, <c>application/x-tar</c>, or gzip-compressed TAR) whose content unpacks
/// into the skill's namespace. Archives are downloaded, extracted to a local directory, and the
/// resulting files are discovered via an internal <see cref="AgentFileSkillsSource"/> that this
/// loader proxies to.
/// </summary>
/// <remarks>
/// Because MCP-delivered skills are treated strictly as instructor-format text, scripts bundled
/// inside an archive are surfaced as readable resources only; they are never discovered as
/// executable scripts.
/// </remarks>
internal sealed partial class ArchiveEntryLoader : IMcpSkillEntryLoader, IDisposable
{
    /// <summary>
    /// The default maximum size, in bytes, of a downloaded archive resource.
    /// </summary>
    internal const long DefaultMaxArchiveSizeBytes = 1L * 1024 * 1024;

    private readonly McpClient _client;
    private readonly AgentMcpSkillsSourceOptions? _options;
    private readonly ILoggerFactory _loggerFactory;
    private readonly ILogger _logger;

    // Serializes the reconcile -> extract -> read sequence so concurrent loads never mutate the
    // shared on-disk directory (or the _archiveSkillsDirectory field) at the same time.
    private readonly SemaphoreSlim _reconcileGate = new(1, 1);

    private string? _archiveSkillsDirectory;

    public ArchiveEntryLoader(McpClient client, AgentMcpSkillsSourceOptions? options, ILoggerFactory loggerFactory)
    {
        this._client = client;
        this._options = options;
        this._loggerFactory = loggerFactory;
        this._logger = loggerFactory.CreateLogger<ArchiveEntryLoader>();
    }

    /// <inheritdoc/>
    public string EntryType => "archive";

    /// <inheritdoc/>
    public async Task<IList<AgentSkill>> LoadAsync(IReadOnlyList<McpSkillIndexEntry> entries, AgentSkillsSourceContext context, CancellationToken cancellationToken)
    {
        // Filter out entries that are missing required fields or have invalid names.
        var archiveEntries = this.FilterValidEntries(entries);

        // The reconcile -> extract -> read sequence mutates a shared on-disk directory and the
        // _archiveSkillsDirectory field, so it must run as a single critical section. Concurrent
        // callers wait here and execute one at a time, keeping the directory consistent.
        await this._reconcileGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            // Determine the target directory from prior state or caller-supplied options.
            var archiveSkillsDirectory = this._archiveSkillsDirectory ?? this._options?.ArchiveSkillsDirectory;

            // Reconcile on-disk state with the current set of advertised skills.
            this.ReconcileArchiveSkillDirectories(archiveSkillsDirectory, archiveEntries);

            if (archiveEntries.Count == 0)
            {
                return [];
            }

            // Resolve or generate the skills directory and ensure it exists on disk.
            this._archiveSkillsDirectory = archiveSkillsDirectory ?? Path.Combine(Directory.GetCurrentDirectory(), Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(this._archiveSkillsDirectory);

            // Download and extract each archive entry into its own subdirectory.
            var skillDirectories = new List<string>(archiveEntries.Count);

            foreach (var entry in archiveEntries)
            {
                skillDirectories.AddRange(await this.TryDownloadAndExtractSkillAsync(entry, this._archiveSkillsDirectory, cancellationToken).ConfigureAwait(false));
            }

            // Delegate discovery of extracted content to a file-based skills source.
            AgentFileSkillsSource fileSource = this.CreateFileSkillsSource(skillDirectories);

            return await fileSource.GetSkillsAsync(context, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            this._reconcileGate.Release();
        }
    }

    /// <summary>
    /// Releases the resources used by this loader.
    /// </summary>
    public void Dispose()
    {
        this._reconcileGate.Dispose();
    }

    /// <summary>
    /// Reconciles the on-disk archive skill directories with the current set of advertised entries.
    /// When no entries are advertised, all existing directories are removed. Otherwise, only stale
    /// directories (not in the current advertised set) are pruned.
    /// </summary>
    private void ReconcileArchiveSkillDirectories(string? archiveSkillsDirectory, List<McpSkillIndexEntry> archiveEntries)
    {
        // Nothing to reconcile if the directory hasn't been established yet.
        if (string.IsNullOrEmpty(archiveSkillsDirectory) || !Directory.Exists(archiveSkillsDirectory))
        {
            return;
        }

        // Server advertises no archive skills - remove all previously extracted directories.
        if (archiveEntries.Count == 0)
        {
            this.ClearSkillsDirectory(archiveSkillsDirectory);
            return;
        }

        // Compare the advertised set against what's on disk; prune any stale leftovers.
        var advertisedSkillNames = archiveEntries
            .Select(e => e.Name!)
            .ToHashSet(OperatingSystem.IsWindows() ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal);

        foreach (string directory in Directory.EnumerateDirectories(archiveSkillsDirectory))
        {
            string name = Path.GetFileName(directory);
            if (advertisedSkillNames.Contains(name))
            {
                continue;
            }

            try
            {
                Directory.Delete(directory, recursive: true);
                LogArchiveSkillPruned(this._logger, name, SanitizePathForLog(directory));
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                LogArchiveSkillPruneFailed(this._logger, name, ex);
            }
        }
    }

    /// <summary>
    /// Removes all subdirectories of the specified directory. Failures on individual directories
    /// are swallowed so that a single locked directory does not prevent cleanup of the others.
    /// </summary>
    private void ClearSkillsDirectory(string archiveSkillsDirectory)
    {
        foreach (var dir in Directory.GetDirectories(archiveSkillsDirectory))
        {
            try
            {
                Directory.Delete(dir, true);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                LogArchiveSkillPruneFailed(this._logger, Path.GetFileName(dir), ex);
            }
        }
    }

    /// <summary>
    /// Creates the internal <see cref="AgentFileSkillsSource"/> that discovers extracted archive
    /// content. Scripts are never treated as executable; the allowed script extensions list is left
    /// empty so that script files are not discovered as runnable scripts.
    /// </summary>
    private AgentFileSkillsSource CreateFileSkillsSource(IReadOnlyList<string> archiveSkillDirectories)
    {
        var fileOptions = new AgentFileSkillsSourceOptions
        {
            AllowedScriptExtensions = [],
            AllowedResourceExtensions = this._options?.ArchiveResourceExtensions,
            SearchDepth = this._options?.ArchiveResourceSearchDepth,
        };

        return new AgentFileSkillsSource(
            archiveSkillDirectories,
            scriptRunner: null,
            options: fileOptions,
            loggerFactory: this._loggerFactory);
    }

    /// <summary>
    /// Downloads the archive for a single skill entry, detects its format, and extracts it into a
    /// subdirectory of <paramref name="archiveSkillsDirectory"/>. Entries that cannot be materialized
    /// (path escape, download failure, unsupported format, or extraction error) are skipped and logged;
    /// partial content is cleaned up on failure.
    /// </summary>
    private async Task<IReadOnlyList<string>> TryDownloadAndExtractSkillAsync(McpSkillIndexEntry entry, string archiveSkillsDirectory, CancellationToken cancellationToken)
    {
        string skillDirectory = Path.Combine(archiveSkillsDirectory, entry.Name!);

        // Defense-in-depth: the skill directory is derived from the server-supplied entry name.
        // Even though invalid names are filtered upstream, verify the resolved path cannot escape
        // the archive skills directory before any file system operation is performed.
        if (!AgentMcpSkillArchiveExtractor.IsPathContainedIn(archiveSkillsDirectory, skillDirectory))
        {
            LogIndexEntrySkipped(this._logger, entry.Name!, "resolved skill directory escapes the archive skills directory");
            return [];
        }

        // Clean the target directory so that content is always freshly extracted.
        if (!this.TryDeleteSkillDirectory(entry.Name!, skillDirectory))
        {
            return [];
        }

        (byte[]? bytes, string? mimeType) = await this.DownloadSkillBytesAsync(entry, cancellationToken).ConfigureAwait(false);
        if (bytes is null)
        {
            return [];
        }

        var format = AgentMcpSkillArchiveExtractor.DetectFormat(bytes, mimeType, entry.Url);
        if (format == ArchiveFormat.Unknown)
        {
            LogIndexEntrySkipped(this._logger, entry.Name!, $"unsupported archive media type '{mimeType ?? "(none)"}'");
            return [];
        }

        try
        {
            AgentMcpSkillArchiveExtractor.Extract(
                bytes,
                format,
                skillDirectory,
                this._options?.ArchiveMaxFileCount,
                this._options?.ArchiveMaxUncompressedSizeBytes);
        }
        catch (Exception ex)
        {
            LogArchiveExtractFailed(this._logger, entry.Name!, ex);

            // Remove any partially-extracted content so it is not later treated as a valid,
            // already-materialized skill by the reuse check above.
            _ = this.TryDeleteSkillDirectory(entry.Name!, skillDirectory);
            return [];
        }

        LogArchiveExtracted(this._logger, entry.Name!, SanitizePathForLog(skillDirectory));

        return [skillDirectory];
    }

    /// <summary>
    /// Downloads and decodes the binary content of a skill's archive resource. Returns <see langword="null"/>
    /// bytes when the resource cannot be read, contains no binary content, or is empty.
    /// </summary>
    private async Task<(byte[]? Bytes, string? MimeType)> DownloadSkillBytesAsync(McpSkillIndexEntry entry, CancellationToken cancellationToken)
    {
        ReadResourceResult result;

        try
        {
#pragma warning disable CA2234 // Pass system uri objects instead of strings
            result = await this._client.ReadResourceAsync(entry.Url!, cancellationToken: cancellationToken).ConfigureAwait(false);
#pragma warning restore CA2234 // Pass system uri objects instead of strings
        }
        catch (McpException ex)
        {
            LogArchiveReadFailed(this._logger, entry.Name!, ex);
            return (null, null);
        }

        BlobResourceContents? blobContent = result.Contents.OfType<BlobResourceContents>().FirstOrDefault();
        if (blobContent is null)
        {
            LogIndexEntrySkipped(this._logger, entry.Name!, "archive resource returned no binary content");
            return (null, null);
        }

        long maxArchiveSizeBytes = this._options?.ArchiveMaxSizeBytes ?? DefaultMaxArchiveSizeBytes;

        byte[] bytes;
        try
        {
            if (blobContent.DecodedData.Length > maxArchiveSizeBytes)
            {
                LogIndexEntrySkipped(this._logger, entry.Name!, $"archive resource exceeds the maximum allowed size ({maxArchiveSizeBytes} bytes)");
                return (null, null);
            }

            bytes = blobContent.DecodedData.ToArray();
        }
        catch (FormatException ex)
        {
            LogArchiveDecodeFailed(this._logger, entry.Name!, ex);
            return (null, null);
        }

        if (bytes.Length == 0)
        {
            LogIndexEntrySkipped(this._logger, entry.Name!, "archive resource returned empty content");
            return (null, null);
        }

        return (bytes, blobContent.MimeType);
    }

    /// <summary>
    /// Filters archive entries to those that are valid for materialization. Entries with missing or
    /// invalid names (not usable as directory names) or missing URLs are excluded and logged.
    /// </summary>
    private List<McpSkillIndexEntry> FilterValidEntries(IReadOnlyList<McpSkillIndexEntry> entries)
    {
        var invalidFileNameChars = Path.GetInvalidFileNameChars();

        var valid = new List<McpSkillIndexEntry>(entries.Count);

        foreach (var entry in entries)
        {
            if (string.IsNullOrWhiteSpace(entry.Name))
            {
                LogIndexEntrySkipped(this._logger, "(unnamed)", "archive entry missing required 'name' field");
                continue;
            }

            if (!IsValidDirectoryName(entry.Name!, invalidFileNameChars))
            {
                LogIndexEntrySkipped(this._logger, entry.Name!, "name contains invalid characters for a directory name");
                continue;
            }

            if (string.IsNullOrWhiteSpace(entry.Url))
            {
                LogIndexEntrySkipped(this._logger, entry.Name!, "missing required 'url' field");
                continue;
            }

            valid.Add(entry);
        }

        return valid;

        static bool IsValidDirectoryName(string value, char[] invalidChars)
        {
            foreach (char c in value)
            {
                if (Array.IndexOf(invalidChars, c) >= 0 || c == Path.DirectorySeparatorChar || c == Path.AltDirectorySeparatorChar)
                {
                    return false;
                }
            }

            // Names consisting solely of dots or whitespace are invalid directory names.
            string trimmed = value.Trim().Trim('.');
            return trimmed.Length > 0;
        }
    }

    /// <summary>
    /// Replaces control characters in a file-system path with <c>?</c> so the path is safe to include
    /// in log messages without risking terminal-escape injection.
    /// </summary>
    private static string SanitizePathForLog(string path)
    {
        char[]? chars = null;
        for (int i = 0; i < path.Length; i++)
        {
            if (char.IsControl(path[i]))
            {
                chars ??= path.ToCharArray();
                chars[i] = '?';
            }
        }

        return chars is null ? path : new string(chars);
    }

    /// <summary>
    /// Attempts to recursively delete a skill directory.
    /// </summary>
    private bool TryDeleteSkillDirectory(string skillName, string directory)
    {
        try
        {
            if (Directory.Exists(directory))
            {
                Directory.Delete(directory, recursive: true);
            }

            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            LogArchiveSkillCleanupFailed(this._logger, skillName, ex);
            return false;
        }
    }

    [LoggerMessage(LogLevel.Debug, "Skipping skill index entry '{SkillName}': {Reason}")]
    private static partial void LogIndexEntrySkipped(ILogger logger, string skillName, string reason);

    [LoggerMessage(LogLevel.Debug, "Extracted archive skill '{SkillName}' to {TargetDirectory}")]
    private static partial void LogArchiveExtracted(ILogger logger, string skillName, string targetDirectory);

    [LoggerMessage(LogLevel.Debug, "Pruned stale archive skill '{SkillName}' at {TargetDirectory}")]
    private static partial void LogArchiveSkillPruned(ILogger logger, string skillName, string targetDirectory);

    [LoggerMessage(LogLevel.Warning, "Failed to prune stale archive skill '{SkillName}'.")]
    private static partial void LogArchiveSkillPruneFailed(ILogger logger, string skillName, Exception exception);

    [LoggerMessage(LogLevel.Warning, "Failed to clean existing archive skill directory for '{SkillName}'.")]
    private static partial void LogArchiveSkillCleanupFailed(ILogger logger, string skillName, Exception exception);

    [LoggerMessage(LogLevel.Warning, "Failed to read archive resource for skill '{SkillName}'.")]
    private static partial void LogArchiveReadFailed(ILogger logger, string skillName, Exception exception);

    [LoggerMessage(LogLevel.Warning, "Failed to decode archive resource for skill '{SkillName}'.")]
    private static partial void LogArchiveDecodeFailed(ILogger logger, string skillName, Exception exception);

    [LoggerMessage(LogLevel.Warning, "Failed to extract archive for skill '{SkillName}'.")]
    private static partial void LogArchiveExtractFailed(ILogger logger, string skillName, Exception exception);
}
