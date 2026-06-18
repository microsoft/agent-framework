// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AIContextProvider"/> that provides file access tools to an agent
/// for saving, reading, deleting, listing, and searching files.
/// </summary>
/// <remarks>
/// <para>
/// The <see cref="FileAccessProvider"/> gives agents the ability to work with files
/// in a folder that the user has granted access to. Unlike <see cref="FileMemoryProvider"/>,
/// which provides session-scoped memory that may be isolated per session, <see cref="FileAccessProvider"/>
/// operates on a shared, persistent folder whose contents are visible across sessions and agents.
/// This makes it suitable for reading input data, writing output artifacts, and working with
/// files that have a lifetime beyond any single agent session.
/// </para>
/// <para>
/// File access is mediated through a <see cref="AgentFileStore"/> abstraction, allowing pluggable
/// backends (in-memory, local file system, remote blob storage, etc.).
/// </para>
/// <para>
/// This provider exposes the following tools to the agent:
/// <list type="bullet">
/// <item><description><c>file_access_save_file</c> — Save a file with the given name and content.</description></item>
/// <item><description><c>file_access_read_file</c> — Read the content of a file by name.</description></item>
/// <item><description><c>file_access_delete_file</c> — Delete a file by name.</description></item>
/// <item><description><c>file_access_list_files</c> — List the direct child file names in a directory.</description></item>
/// <item><description><c>file_access_list_subdirectories</c> — List the direct child subdirectory names in a directory.</description></item>
/// <item><description><c>file_access_search_files</c> — Recursively search file contents using a regular expression pattern.</description></item>
/// </list>
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileAccessProvider : AIContextProvider
{
    private const string DefaultInstructions =
        """
        ## File Access
        You have access to a shared file storage area via the `file_access_*` tools for reading, writing, and managing files.
        These files persist beyond the current session and may be shared across sessions or agents.
        Use these tools to read input data provided by the user, write output artifacts, and manage any files the user has asked you to work with.

        - Never delete or overwrite existing files unless the user has explicitly asked you to do so.
        - Files may be organized into subdirectories. Use `file_access_list_files` and `file_access_list_subdirectories` to explore the tree level by level,
          or `file_access_search_files` to search file contents recursively across the whole store.
        """;

    private readonly AgentFileStore _fileStore;
    private readonly string _instructions;
    private AITool[]? _tools;

    /// <summary>
    /// Initializes a new instance of the <see cref="FileAccessProvider"/> class.
    /// </summary>
    /// <param name="fileStore">
    /// The file store implementation used for storage operations.
    /// The store should already be scoped to the desired folder or storage location.
    /// </param>
    /// <param name="options">Optional settings that control provider behavior. When <see langword="null"/>, defaults are used.</param>
    /// <exception cref="System.ArgumentNullException">Thrown when <paramref name="fileStore"/> is <see langword="null"/>.</exception>
    public FileAccessProvider(AgentFileStore fileStore, FileAccessProviderOptions? options = null)
    {
        Throw.IfNull(fileStore);

        this._fileStore = fileStore;
        this._instructions = options?.Instructions ?? DefaultInstructions;
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => [];

    /// <inheritdoc />
    protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        return new ValueTask<AIContext>(new AIContext
        {
            Instructions = this._instructions,
            Tools = this._tools ??= this.CreateTools(),
        });
    }

    /// <summary>
    /// Save a file with the given name and content. By default, does not overwrite an existing file unless overwrite is set to true.
    /// </summary>
    /// <param name="fileName">The name of the file to save.</param>
    /// <param name="content">The content to write to the file.</param>
    /// <param name="overwrite">Whether to overwrite the file if it already exists.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A confirmation message.</returns>
    [Description("Save a file with the given name and content. By default, does not overwrite an existing file unless overwrite is set to true.")]
    private async Task<string> SaveFileAsync(string fileName, string content, bool overwrite = false, CancellationToken cancellationToken = default)
    {
        string path = StorePaths.NormalizeRelativePath(fileName);

        if (!overwrite && await this._fileStore.FileExistsAsync(path, cancellationToken).ConfigureAwait(false))
        {
            return $"File '{fileName}' already exists. To replace it, save again with overwrite set to true.";
        }

        await this._fileStore.WriteFileAsync(path, content, cancellationToken).ConfigureAwait(false);
        return $"File '{fileName}' saved.";
    }

    /// <summary>
    /// Read the content of a file by name. Returns the file content or a message indicating the file was not found.
    /// </summary>
    /// <param name="fileName">The name of the file to read.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>The file content or a not-found message.</returns>
    [Description("Read the content of a file by name. Returns the file content or a message indicating the file was not found.")]
    private async Task<string> ReadFileAsync(string fileName, CancellationToken cancellationToken = default)
    {
        string path = StorePaths.NormalizeRelativePath(fileName);
        string? content = await this._fileStore.ReadFileAsync(path, cancellationToken).ConfigureAwait(false);
        return content ?? $"File '{fileName}' not found.";
    }

    /// <summary>
    /// Delete a file by name.
    /// </summary>
    /// <param name="fileName">The name of the file to delete.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A confirmation or not-found message.</returns>
    [Description("Delete a file by name.")]
    private async Task<string> DeleteFileAsync(string fileName, CancellationToken cancellationToken = default)
    {
        string path = StorePaths.NormalizeRelativePath(fileName);
        bool deleted = await this._fileStore.DeleteFileAsync(path, cancellationToken).ConfigureAwait(false);
        return deleted ? $"File '{fileName}' deleted." : $"File '{fileName}' not found.";
    }

    /// <summary>
    /// List the direct child file names of a directory. Omit <paramref name="directory"/> (or pass an empty string)
    /// to list the store root. To enumerate files in a subdirectory, pass its relative path.
    /// </summary>
    /// <param name="directory">The relative directory path to list. Omit or pass an empty string to list the store root.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A list of file names.</returns>
    [Description("List the direct child file names of a directory. Omit the directory (or pass an empty string) to list the root. To enumerate files in a subdirectory, pass its relative path, for example \"reports\" or \"reports/2024\".")]
    private async Task<List<string>> ListFilesAsync(string? directory = null, CancellationToken cancellationToken = default)
    {
        string target = string.IsNullOrWhiteSpace(directory) ? string.Empty : directory;
        IReadOnlyList<string> fileNames = await this._fileStore.ListFilesAsync(target, cancellationToken).ConfigureAwait(false);
        return new List<string>(fileNames);
    }

    /// <summary>
    /// List the direct child subdirectory names of a directory. Omit <paramref name="directory"/> (or pass an empty string)
    /// to list the store root. To enumerate subdirectories of a subdirectory, pass its relative path.
    /// </summary>
    /// <param name="directory">The relative directory path to list. Omit or pass an empty string to list the store root.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A list of subdirectory names.</returns>
    [Description("List the direct child subdirectory names of a directory. Omit the directory (or pass an empty string) to list the root. To enumerate subdirectories of a subdirectory, pass its relative path, for example \"reports\" or \"reports/2024\". Use this together with file_access_list_files to explore the directory tree level by level.")]
    private async Task<List<string>> ListSubdirectoriesAsync(string? directory = null, CancellationToken cancellationToken = default)
    {
        string target = string.IsNullOrWhiteSpace(directory) ? string.Empty : directory;
        IReadOnlyList<string> directoryNames = await this._fileStore.ListDirectoriesAsync(target, cancellationToken).ConfigureAwait(false);
        return new List<string>(directoryNames);
    }

    /// <summary>
    /// Search the contents of all files in the store (recursively) using a regular expression pattern (case-insensitive).
    /// Optionally filter which files to search using a glob pattern.
    /// </summary>
    /// <param name="regexPattern">A regular expression pattern to match against file contents (case-insensitive).</param>
    /// <param name="filePattern">An optional glob pattern to filter which files to search, matched against each file's path relative to the store root. Use <c>**</c> to match across subdirectories (e.g., "**/*.md"). Leave empty or omit to search all files.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A list of search results whose file names are paths relative to the store root.</returns>
    [Description(
        """
        Search the contents of all files in the store (recursively, across all subdirectories) using a regular expression pattern (case-insensitive).
        Optionally filter which files to search using a glob pattern matched against each file's path relative to the store root:
        - '*' matches within a single path segment
        - '**' matches across subdirectories, so use \"**/*.md\" to match markdown files at any depth, or \"reports/**\" to restrict the search to the 'reports' subtree.
        
        Returns matching results whose file names are paths relative to the store root (usable with file_access_read_file), along with snippets and matching lines with line numbers.
        """)]
    private async Task<List<FileSearchResult>> SearchFilesAsync(string regexPattern, string? filePattern = null, CancellationToken cancellationToken = default)
    {
        string? pattern = string.IsNullOrWhiteSpace(filePattern) ? null : filePattern;
        IReadOnlyList<FileSearchResult> results = await this._fileStore.SearchFilesAsync(string.Empty, regexPattern, pattern, recursive: true, cancellationToken).ConfigureAwait(false);
        return new List<FileSearchResult>(results);
    }

    private AITool[] CreateTools()
    {
        var serializerOptions = AgentJsonUtilities.DefaultOptions;

        return
        [
            AIFunctionFactory.Create(this.SaveFileAsync, new AIFunctionFactoryOptions { Name = "file_access_save_file", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.ReadFileAsync, new AIFunctionFactoryOptions { Name = "file_access_read_file", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.DeleteFileAsync, new AIFunctionFactoryOptions { Name = "file_access_delete_file", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.ListFilesAsync, new AIFunctionFactoryOptions { Name = "file_access_list_files", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.ListSubdirectoriesAsync, new AIFunctionFactoryOptions { Name = "file_access_list_subdirectories", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.SearchFilesAsync, new AIFunctionFactoryOptions { Name = "file_access_search_files", SerializerOptions = serializerOptions }),
        ];
    }
}
