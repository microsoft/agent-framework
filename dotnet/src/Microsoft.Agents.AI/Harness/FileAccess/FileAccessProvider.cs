// Copyright (c) Microsoft. All rights reserved.

using System;
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
/// <para>
/// All of these tools always require approval: each is exposed as an <see cref="ApprovalRequiredAIFunction"/>.
/// </para>
/// <para>
/// To auto-approve these tools without prompting, use the <see cref="ToolApprovalAgent"/> and add one of the provided rules to
/// <see cref="ToolApprovalAgentOptions.AutoApprovalRules"/>:
/// <list type="bullet">
/// <item><description>
/// <see cref="ReadOnlyToolsAutoApprovalRule"/> — auto-approves only the read-only tools (read, list, list subdirectories,
/// and search), while still prompting for the tools that modify the store (save and delete).
/// </description></item>
/// <item><description>
/// <see cref="AllToolsAutoApprovalRule"/> — auto-approves every file access tool, including save and delete.
/// </description></item>
/// </list>
/// For example, to auto-approve all file access tools:
/// <code>
/// builder.UseToolApproval(new ToolApprovalAgentOptions
/// {
///     AutoApprovalRules = [FileAccessProvider.AllToolsAutoApprovalRule],
/// });
/// </code>
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileAccessProvider : AIContextProvider
{
    /// <summary>The name of the tool that saves a file.</summary>
    public const string SaveFileToolName = "file_access_save_file";

    /// <summary>The name of the tool that reads a file.</summary>
    public const string ReadFileToolName = "file_access_read_file";

    /// <summary>The name of the tool that deletes a file.</summary>
    public const string DeleteFileToolName = "file_access_delete_file";

    /// <summary>The name of the tool that lists the files in a directory.</summary>
    public const string ListFilesToolName = "file_access_list_files";

    /// <summary>The name of the tool that lists the subdirectories of a directory.</summary>
    public const string ListSubdirectoriesToolName = "file_access_list_subdirectories";

    /// <summary>The name of the tool that searches file contents.</summary>
    public const string SearchFilesToolName = "file_access_search_files";

    /// <summary>The names of the tools that only read from (never modify) the file store.</summary>
    private static readonly HashSet<string> s_readOnlyToolNames = new(StringComparer.Ordinal)
    {
        ReadFileToolName,
        ListFilesToolName,
        ListSubdirectoriesToolName,
        SearchFilesToolName,
    };

    /// <summary>The names of all tools exposed by this provider.</summary>
    private static readonly HashSet<string> s_allToolNames = new(StringComparer.Ordinal)
    {
        SaveFileToolName,
        ReadFileToolName,
        DeleteFileToolName,
        ListFilesToolName,
        ListSubdirectoriesToolName,
        SearchFilesToolName,
    };

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
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="fileStore"/> is <see langword="null"/>.</exception>
    public FileAccessProvider(AgentFileStore fileStore, FileAccessProviderOptions? options = null)
    {
        Throw.IfNull(fileStore);

        this._fileStore = fileStore;
        this._instructions = options?.Instructions ?? DefaultInstructions;
    }

    /// <summary>
    /// Gets an auto-approval rule that approves the read-only file access tools
    /// (<see cref="ReadFileToolName"/>, <see cref="ListFilesToolName"/>,
    /// <see cref="ListSubdirectoriesToolName"/>, and <see cref="SearchFilesToolName"/>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// The tools exposed by <see cref="FileAccessProvider"/> always require approval. Add this rule to
    /// <see cref="ToolApprovalAgentOptions.AutoApprovalRules"/> to automatically approve only the tools
    /// that read from the file store, while still prompting for tools that modify it
    /// (<see cref="SaveFileToolName"/> and <see cref="DeleteFileToolName"/>).
    /// </para>
    /// <para>
    /// The rule matches on the tool name, returning <see langword="true"/> for read-only file access tools
    /// and <see langword="false"/> for all other tool calls so that subsequent rules continue to be evaluated.
    /// </para>
    /// </remarks>
    public static Func<FunctionCallContent, ValueTask<bool>> ReadOnlyToolsAutoApprovalRule { get; } =
        functionCall => new ValueTask<bool>(s_readOnlyToolNames.Contains(functionCall.Name));

    /// <summary>
    /// Gets an auto-approval rule that approves all file access tools, including the tools that modify the
    /// file store (<see cref="SaveFileToolName"/> and <see cref="DeleteFileToolName"/>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// The tools exposed by <see cref="FileAccessProvider"/> always require approval. Add this rule to
    /// <see cref="ToolApprovalAgentOptions.AutoApprovalRules"/> to automatically approve every file access
    /// tool without prompting the user.
    /// </para>
    /// <para>
    /// The rule matches on the tool name, returning <see langword="true"/> for any file access tool
    /// and <see langword="false"/> for all other tool calls so that subsequent rules continue to be evaluated.
    /// </para>
    /// </remarks>
    public static Func<FunctionCallContent, ValueTask<bool>> AllToolsAutoApprovalRule { get; } =
        functionCall => new ValueTask<bool>(s_allToolNames.Contains(functionCall.Name));

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

        // All file access tools always require approval. Callers can use the
        // ReadOnlyToolsAutoApprovalRule or AllToolsAutoApprovalRule with the ToolApprovalAgent
        // to automatically approve these tools.
        return
        [
            new ApprovalRequiredAIFunction(AIFunctionFactory.Create(this.SaveFileAsync, new AIFunctionFactoryOptions { Name = SaveFileToolName, SerializerOptions = serializerOptions })),
            new ApprovalRequiredAIFunction(AIFunctionFactory.Create(this.ReadFileAsync, new AIFunctionFactoryOptions { Name = ReadFileToolName, SerializerOptions = serializerOptions })),
            new ApprovalRequiredAIFunction(AIFunctionFactory.Create(this.DeleteFileAsync, new AIFunctionFactoryOptions { Name = DeleteFileToolName, SerializerOptions = serializerOptions })),
            new ApprovalRequiredAIFunction(AIFunctionFactory.Create(this.ListFilesAsync, new AIFunctionFactoryOptions { Name = ListFilesToolName, SerializerOptions = serializerOptions })),
            new ApprovalRequiredAIFunction(AIFunctionFactory.Create(this.ListSubdirectoriesAsync, new AIFunctionFactoryOptions { Name = ListSubdirectoriesToolName, SerializerOptions = serializerOptions })),
            new ApprovalRequiredAIFunction(AIFunctionFactory.Create(this.SearchFilesAsync, new AIFunctionFactoryOptions { Name = SearchFilesToolName, SerializerOptions = serializerOptions })),
        ];
    }
}
