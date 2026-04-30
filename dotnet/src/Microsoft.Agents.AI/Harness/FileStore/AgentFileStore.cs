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
    public abstract Task WriteFileAsync(string path, string content, CancellationToken cancellationToken = default);

    /// <summary>
    /// Reads the content of a file.
    /// </summary>
    /// <param name="path">The relative path of the file to read.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>The file content, or <see langword="null"/> if the file does not exist.</returns>
    public abstract Task<string?> ReadFileAsync(string path, CancellationToken cancellationToken = default);

    /// <summary>
    /// Deletes a file.
    /// </summary>
    /// <param name="path">The relative path of the file to delete.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns><see langword="true"/> if the file was deleted; <see langword="false"/> if it did not exist.</returns>
    public abstract Task<bool> DeleteFileAsync(string path, CancellationToken cancellationToken = default);

    /// <summary>
    /// Lists files in a directory.
    /// </summary>
    /// <param name="directory">The relative path of the directory to list. Use an empty string for the root.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A list of file names in the specified directory (direct children only).</returns>
    public abstract Task<IReadOnlyList<string>> ListFilesAsync(string directory, CancellationToken cancellationToken = default);

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
    /// <param name="filePattern">
    /// An optional glob pattern to filter which files are searched (e.g., <c>"*.md"</c>, <c>"research*"</c>).
    /// When <see langword="null"/>, all files in the directory are searched.
    /// Uses standard glob syntax from <see cref="Matcher"/>.
    /// </param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A list of search results with matching file names, snippets, and matching lines.</returns>
    public abstract Task<IReadOnlyList<FileSearchResult>> SearchFilesAsync(string directory, string regexPattern, string? filePattern = null, CancellationToken cancellationToken = default);

    /// <summary>
    /// Ensures a directory exists, creating it if necessary.
    /// </summary>
    /// <param name="path">The relative path of the directory to create.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    public abstract Task CreateDirectoryAsync(string path, CancellationToken cancellationToken = default);
}
