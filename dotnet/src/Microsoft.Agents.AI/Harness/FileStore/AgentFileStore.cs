// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.FileSystemGlobbing;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides an abstract base class for file storage operations.
/// </summary>
/// <remarks>
/// <para>
/// All paths are relative to an implementation-defined root. Implementations may map these
/// paths to a local file system, in-memory store, remote blob storage, or other mechanisms.
/// </para>
/// <para>
/// Paths use forward slashes as separators and must not escape the root (e.g., via <c>..</c> segments).
/// It is up to each implementation to ensure that this is enforced.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class AgentFileStore
{
    /// <summary>
    /// Writes content to a file, creating or overwriting it.
    /// </summary>
    /// <param name="path">The relative path of the file to write.</param>
    /// <param name="content">The content to write to the file.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    public abstract Task WriteAsync(string path, string content, CancellationToken cancellationToken = default);

    /// <summary>
    /// Reads the content of a file.
    /// </summary>
    /// <param name="path">The relative path of the file to read.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>The file content, or <see langword="null"/> if the file does not exist.</returns>
    public abstract Task<string?> ReadAsync(string path, CancellationToken cancellationToken = default);

    /// <summary>
    /// Deletes a file.
    /// </summary>
    /// <param name="path">The relative path of the file to delete.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns><see langword="true"/> if the file was deleted; <see langword="false"/> if it did not exist.</returns>
    public abstract Task<bool> DeleteAsync(string path, CancellationToken cancellationToken = default);

    /// <summary>
    /// Lists the direct children (files and subdirectories) of a directory.
    /// </summary>
    /// <param name="directory">The relative path of the directory to list. Use an empty string for the root.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>
    /// A list of the direct children of the specified directory as <see cref="FileStoreEntry"/> instances.
    /// Subdirectories are listed before files.
    /// </returns>
    public abstract Task<IReadOnlyList<FileStoreEntry>> ListChildrenAsync(string directory, CancellationToken cancellationToken = default);

    /// <summary>
    /// Checks whether a file exists.
    /// </summary>
    /// <param name="path">The relative path of the file to check.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns><see langword="true"/> if the file exists; otherwise, <see langword="false"/>.</returns>
    public abstract Task<bool> FileExistsAsync(string path, CancellationToken cancellationToken = default);

    /// <summary>
    /// Searches for files whose content matches a regular expression pattern.
    /// </summary>
    /// <param name="directory">The relative path of the directory to search. Use an empty string for the root.</param>
    /// <param name="regexPattern">
    /// A regular expression pattern to match against file contents. The pattern is matched case-insensitively.
    /// For example, <c>"error|warning"</c> matches lines containing "error" or "warning".
    /// </param>
    /// <param name="globPattern">
    /// An optional glob pattern to filter which files are searched (e.g., <c>"*.md"</c>, <c>"research*"</c>).
    /// When <see langword="null"/>, all files are searched.
    /// Uses standard glob syntax from <see cref="Matcher"/>, matched against each file's path relative to
    /// <paramref name="directory"/>. Use <c>**</c> to match across subdirectories (e.g., <c>"**/*.md"</c>).
    /// </param>
    /// <param name="recursive">
    /// When <see langword="true"/>, all descendant files of <paramref name="directory"/> are searched.
    /// When <see langword="false"/> (default), only the direct children of <paramref name="directory"/> are searched.
    /// </param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>
    /// A list of search results. Each result's <see cref="FileSearchResult.FileName"/> is the matching file's
    /// path relative to <paramref name="directory"/>.
    /// </returns>
    public abstract Task<IReadOnlyList<FileSearchResult>> SearchAsync(string directory, string regexPattern, string? globPattern = null, bool recursive = false, CancellationToken cancellationToken = default);

    /// <summary>
    /// Ensures a directory exists, creating it if necessary.
    /// </summary>
    /// <param name="path">The relative path of the directory to create.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    public abstract Task CreateDirectoryAsync(string path, CancellationToken cancellationToken = default);
}
