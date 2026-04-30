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
/// <item><description><c>SaveFile</c> — Save a file with the given name and content.</description></item>
/// <item><description><c>ReadFile</c> — Read the content of a file by name.</description></item>
/// <item><description><c>DeleteFile</c> — Delete a file by name.</description></item>
/// <item><description><c>ListFiles</c> — List all file names.</description></item>
/// <item><description><c>SearchFiles</c> — Search file contents using a regular expression pattern.</description></item>
/// </list>
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public class FileAccessProvider : AIContextProvider
{
    private const string FallbackDefaultInstructions =
        """
        ## File Access
        You have access to a shared file storage area via the `FileAccess_*` tools for reading, writing, and managing files.
        These files persist beyond the current session and may be shared across sessions or agents.
        Use these tools to read input data provided by the user, write output artifacts, and manage any files the user has asked you to work with.

        - Never delete or overwrite existing files unless the user has explicitly asked you to do so.
        """;

    private readonly string? _instructionsOverride;
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

        this.FileStore = fileStore;
        this._instructionsOverride = options?.Instructions;
    }

    /// <summary>
    /// Gets the default instructions surfaced to the agent when no override is supplied via <see cref="FileAccessProviderOptions.Instructions"/>.
    /// </summary>
    /// <remarks>
    /// Override this property in a derived class to provide subclass-specific default instructions
    /// (for example, instructions describing a higher-fidelity coding-workspace surface).
    /// </remarks>
    protected virtual string DefaultInstructions => FallbackDefaultInstructions;

    /// <summary>
    /// Gets the file store backing this provider. Available to derived classes that need direct access
    /// for additional operations beyond the base universal contract.
    /// </summary>
    protected AgentFileStore FileStore { get; }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => [];

    /// <inheritdoc />
    protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        return new ValueTask<AIContext>(new AIContext
        {
            Instructions = this._instructionsOverride ?? this.DefaultInstructions,
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

        if (!overwrite && await this.FileStore.FileExistsAsync(path, cancellationToken).ConfigureAwait(false))
        {
            return $"File '{fileName}' already exists. To replace it, save again with overwrite set to true.";
        }

        await this.FileStore.WriteFileAsync(path, content, cancellationToken).ConfigureAwait(false);
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
        string? content = await this.FileStore.ReadFileAsync(path, cancellationToken).ConfigureAwait(false);
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
        bool deleted = await this.FileStore.DeleteFileAsync(path, cancellationToken).ConfigureAwait(false);
        return deleted ? $"File '{fileName}' deleted." : $"File '{fileName}' not found.";
    }

    /// <summary>
    /// List all file names.
    /// </summary>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A list of file names.</returns>
    [Description("List all file names.")]
    private async Task<List<string>> ListFilesAsync(CancellationToken cancellationToken = default)
    {
        IReadOnlyList<string> fileNames = await this.FileStore.ListFilesAsync(string.Empty, cancellationToken).ConfigureAwait(false);
        return new List<string>(fileNames);
    }

    /// <summary>
    /// Search file contents using a regular expression pattern (case-insensitive).
    /// Optionally filter which files to search using a glob pattern.
    /// </summary>
    /// <param name="regexPattern">A regular expression pattern to match against file contents (case-insensitive).</param>
    /// <param name="filePattern">An optional glob pattern to filter which files to search (e.g., "*.md", "research*"). Leave empty or omit to search all files.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A list of search results with matching file names, snippets, and matching lines.</returns>
    [Description("Search file contents using a regular expression pattern (case-insensitive). Optionally filter which files to search using a glob pattern (e.g., \"*.md\", \"research*\"). Returns matching file names, snippets, and matching lines with line numbers.")]
    private async Task<List<FileSearchResult>> SearchFilesAsync(string regexPattern, string? filePattern = null, CancellationToken cancellationToken = default)
    {
        string? pattern = string.IsNullOrWhiteSpace(filePattern) ? null : filePattern;
        IReadOnlyList<FileSearchResult> results = await this.FileStore.SearchFilesAsync(string.Empty, regexPattern, pattern, cancellationToken).ConfigureAwait(false);
        return new List<FileSearchResult>(results);
    }

    /// <summary>
    /// Builds the list of tools this provider exposes to the agent. The base implementation returns
    /// the five universal file-access tools (Save/Read/Delete/List/Search). Override in a derived class
    /// to add or replace tools — typically by appending to <c>base.CreateTools()</c>.
    /// </summary>
    protected virtual AITool[] CreateTools()
    {
        var serializerOptions = AgentJsonUtilities.DefaultOptions;

        return
        [
            AIFunctionFactory.Create(this.SaveFileAsync, new AIFunctionFactoryOptions { Name = "FileAccess_SaveFile", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.ReadFileAsync, new AIFunctionFactoryOptions { Name = "FileAccess_ReadFile", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.DeleteFileAsync, new AIFunctionFactoryOptions { Name = "FileAccess_DeleteFile", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.ListFilesAsync, new AIFunctionFactoryOptions { Name = "FileAccess_ListFiles", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.SearchFilesAsync, new AIFunctionFactoryOptions { Name = "FileAccess_SearchFiles", SerializerOptions = serializerOptions }),
        ];
    }
}
