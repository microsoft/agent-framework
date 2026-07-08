// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.FileSystemGlobbing;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AIContextProvider"/> that provides file access tools to an agent
/// for writing, reading, deleting, listing, searching, and editing files.
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
/// <item><description><c>file_access_write</c> — Write a file with the given name and content.</description></item>
/// <item><description><c>file_access_read</c> — Read the content of a file by name.</description></item>
/// <item><description><c>file_access_delete</c> — Delete a file by name.</description></item>
/// <item><description><c>file_access_ls</c> — List the direct child files and subdirectories of a directory.</description></item>
/// <item><description><c>file_access_grep</c> — Recursively search file contents using a regular expression pattern.</description></item>
/// <item><description><c>file_access_replace</c> — Replace occurrences of a substring within a file.</description></item>
/// <item><description><c>file_access_replace_lines</c> — Replace whole lines within a file.</description></item>
/// </list>
/// When <see cref="FileAccessProviderOptions.DisableWriteTools"/> is set, only the read-only tools
/// (<c>file_access_read</c>, <c>file_access_ls</c>, and <c>file_access_grep</c>) are exposed.
/// </para>
/// <para>
/// By default, all of these tools require approval: each is exposed as an <see cref="ApprovalRequiredAIFunction"/>.
/// Approval can be disabled per group via <see cref="FileAccessProviderOptions.DisableReadOnlyToolApproval"/>
/// (read, ls, and grep) and <see cref="FileAccessProviderOptions.DisableWriteToolApproval"/>
/// (write, delete, replace, and replace_lines).
/// </para>
/// <para>
/// To auto-approve these tools without prompting, use the <see cref="ToolApprovalAgent"/> and add one of the provided rules to
/// <see cref="ToolApprovalAgentOptions.AutoApprovalRules"/>:
/// <list type="bullet">
/// <item><description>
/// <see cref="ReadOnlyToolsAutoApprovalRule"/> — auto-approves only the read-only tools (read, ls,
/// and grep), while still prompting for the tools that modify the store (write, delete, replace, and replace_lines).
/// </description></item>
/// <item><description>
/// <see cref="AllToolsAutoApprovalRule"/> — auto-approves every file access tool, including the tools that modify the store.
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
public sealed class FileAccessProvider : AIContextProvider, IDisposable
{
    /// <summary>The name of the tool that writes a file.</summary>
    public const string WriteToolName = "file_access_write";

    /// <summary>The name of the tool that reads a file.</summary>
    public const string ReadFileToolName = "file_access_read";

    /// <summary>The name of the tool that deletes a file.</summary>
    public const string DeleteFileToolName = "file_access_delete";

    /// <summary>The name of the tool that lists the files and subdirectories in a directory.</summary>
    public const string LsToolName = "file_access_ls";

    /// <summary>The name of the tool that searches file contents.</summary>
    public const string GrepToolName = "file_access_grep";

    /// <summary>The name of the tool that replaces occurrences of a substring within a file.</summary>
    public const string ReplaceToolName = "file_access_replace";

    /// <summary>The name of the tool that replaces whole lines within a file.</summary>
    public const string ReplaceLinesToolName = "file_access_replace_lines";

    /// <summary>The names of the tools that only read from (never modify) the file store.</summary>
    private static readonly HashSet<string> s_readOnlyToolNames = new(StringComparer.Ordinal)
    {
        ReadFileToolName,
        LsToolName,
        GrepToolName,
    };

    /// <summary>The names of all tools exposed by this provider.</summary>
    private static readonly HashSet<string> s_allToolNames = new(StringComparer.Ordinal)
    {
        WriteToolName,
        ReadFileToolName,
        DeleteFileToolName,
        LsToolName,
        GrepToolName,
        ReplaceToolName,
        ReplaceLinesToolName,
    };

    private const string DefaultInstructions =
        """
        ## File Access
        You have access to a shared file storage area via the `file_access_*` tools for reading, writing, and managing files.
        These files persist beyond the current session and may be shared across sessions or agents.
        Use these tools to read input data provided by the user, write output artifacts, and manage any files the user has asked you to work with.

        - Never delete or overwrite existing files unless the user has explicitly asked you to do so.
        - Files may be organized into subdirectories. Use `file_access_ls` to explore the tree level by level,
          or `file_access_grep` to search file contents recursively across the whole store.
        - To make small edits to an existing file, prefer `file_access_replace` (substring replacement) or
          `file_access_replace_lines` (whole-line replacement) over rewriting the whole file.
        """;

    private readonly AgentFileStore _fileStore;
    private readonly string _instructions;
    private readonly bool _disableWriteTools;
    private readonly bool _disableReadOnlyToolApproval;
    private readonly bool _disableWriteToolApproval;
    private readonly SemaphoreSlim _writeLock = new(1, 1);
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
        this._disableWriteTools = options?.DisableWriteTools ?? false;
        this._disableReadOnlyToolApproval = options?.DisableReadOnlyToolApproval ?? false;
        this._disableWriteToolApproval = options?.DisableWriteToolApproval ?? false;
    }

    /// <summary>
    /// Gets an auto-approval rule that approves the read-only file access tools
    /// (<see cref="ReadFileToolName"/>, <see cref="LsToolName"/>, and <see cref="GrepToolName"/>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// By default, the tools exposed by <see cref="FileAccessProvider"/> require approval. Add this rule to
    /// <see cref="ToolApprovalAgentOptions.AutoApprovalRules"/> to automatically approve only the tools
    /// that read from the file store, while still prompting for tools that modify it
    /// (<see cref="WriteToolName"/>, <see cref="DeleteFileToolName"/>, <see cref="ReplaceToolName"/>,
    /// and <see cref="ReplaceLinesToolName"/>).
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
    /// file store (<see cref="WriteToolName"/>, <see cref="DeleteFileToolName"/>, <see cref="ReplaceToolName"/>,
    /// and <see cref="ReplaceLinesToolName"/>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// By default, the tools exposed by <see cref="FileAccessProvider"/> require approval. Add this rule to
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

    /// <summary>
    /// Releases the resources used by the <see cref="FileAccessProvider"/>.
    /// </summary>
    public void Dispose()
    {
        this._writeLock.Dispose();
    }

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
    /// Write a file with the given name and content. By default, does not overwrite an existing file unless overwrite is set to true.
    /// </summary>
    /// <param name="fileName">The name of the file to write.</param>
    /// <param name="content">The content to write to the file.</param>
    /// <param name="overwrite">Whether to overwrite the file if it already exists.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A confirmation message.</returns>
    [Description("Write a file with the given name and content. By default, does not overwrite an existing file unless overwrite is set to true.")]
    private async Task<string> WriteAsync(string fileName, string content, bool overwrite = false, CancellationToken cancellationToken = default)
    {
        string path = StorePaths.NormalizeRelativePath(fileName);

        await this._writeLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (!overwrite && await this._fileStore.FileExistsAsync(path, cancellationToken).ConfigureAwait(false))
            {
                return $"File '{fileName}' already exists. To replace it, write again with overwrite set to true.";
            }

            await this._fileStore.WriteAsync(path, content, cancellationToken).ConfigureAwait(false);
        }
        finally
        {
            this._writeLock.Release();
        }

        return $"File '{fileName}' written.";
    }

    /// <summary>
    /// Read the content of a file by name. Returns the file content or a message indicating the file was not found.
    /// </summary>
    /// <param name="fileName">The name of the file to read.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>The file content or a not-found message.</returns>
    [Description("Read the content of a file by name. Returns the file content or a message indicating the file was not found.")]
    private async Task<string> ReadAsync(string fileName, CancellationToken cancellationToken = default)
    {
        string path = StorePaths.NormalizeRelativePath(fileName);
        string? content = await this._fileStore.ReadAsync(path, cancellationToken).ConfigureAwait(false);
        return content ?? $"File '{fileName}' not found.";
    }

    /// <summary>
    /// Delete a file by name.
    /// </summary>
    /// <param name="fileName">The name of the file to delete.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A confirmation or not-found message.</returns>
    [Description("Delete a file by name.")]
    private async Task<string> DeleteAsync(string fileName, CancellationToken cancellationToken = default)
    {
        string path = StorePaths.NormalizeRelativePath(fileName);

        await this._writeLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            bool deleted = await this._fileStore.DeleteAsync(path, cancellationToken).ConfigureAwait(false);
            return deleted ? $"File '{fileName}' deleted." : $"File '{fileName}' not found.";
        }
        finally
        {
            this._writeLock.Release();
        }
    }

    /// <summary>
    /// List the direct child files and subdirectories of a directory. Omit <paramref name="directory"/> (or pass an empty string)
    /// to list the store root. Optionally filter entries with a glob pattern.
    /// </summary>
    /// <param name="directory">The relative directory path to list. Omit or pass an empty string to list the store root.</param>
    /// <param name="globPattern">An optional glob pattern (e.g., "*.md") matched against entry names to filter the listing.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A list of entries, each with a name and a type of "file" or "directory" (subdirectories first).</returns>
    [Description("List the direct child files and subdirectories of a directory. Omit the directory (or pass an empty string) to list the root. To enumerate a subdirectory, pass its relative path, for example \"reports\" or \"reports/2024\". Optionally filter entries with a glob_pattern (e.g. \"*.md\"). Subdirectories are listed before files, and each entry has a name and a type of \"file\" or \"directory\".")]
    private async Task<List<FileStoreEntry>> LsAsync(string? directory = null, string? globPattern = null, CancellationToken cancellationToken = default)
    {
        string target = string.IsNullOrWhiteSpace(directory) ? string.Empty : directory!;
        IReadOnlyList<FileStoreEntry> entries = await this._fileStore.ListChildrenAsync(target, cancellationToken).ConfigureAwait(false);

        Matcher? matcher = string.IsNullOrWhiteSpace(globPattern) ? null : StorePaths.CreateGlobMatcher(globPattern!);
        return entries.Where(entry => StorePaths.MatchesGlob(entry.Name, matcher)).ToList();
    }

    /// <summary>
    /// Replace occurrences of <paramref name="oldString"/> with <paramref name="newString"/> in a file.
    /// </summary>
    /// <param name="fileName">The name of the file to modify.</param>
    /// <param name="oldString">The substring to find and replace.</param>
    /// <param name="newString">The replacement text.</param>
    /// <param name="replaceAll">When <see langword="true"/>, replace every occurrence; otherwise fail unless exactly one occurrence exists.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A confirmation message including the number of occurrences replaced, or a failure message.</returns>
    [Description("Replace occurrences of old_string with new_string in a file. Fails if old_string is not found, or if it occurs more than once and replace_all is false. Returns the number of occurrences replaced.")]
    private async Task<string> ReplaceAsync(string fileName, string oldString, string newString, bool replaceAll = false, CancellationToken cancellationToken = default)
    {
        await this._writeLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            string path = StorePaths.NormalizeRelativePath(fileName);
            string? content = await this._fileStore.ReadAsync(path, cancellationToken).ConfigureAwait(false);
            if (content is null)
            {
                return $"File '{fileName}' not found.";
            }

            (string newContent, int count) = FileEditor.ApplyReplace(content, oldString, newString, replaceAll);
            await this._fileStore.WriteAsync(path, newContent, cancellationToken).ConfigureAwait(false);
            return $"Replaced {count} occurrence(s) in '{fileName}'.";
        }
        finally
        {
            this._writeLock.Release();
        }
    }

    /// <summary>
    /// Replace lines in a file. Provide a list of edits, each with a 1-based line number and the literal
    /// replacement text; an empty replacement deletes the line.
    /// </summary>
    /// <param name="fileName">The name of the file to modify.</param>
    /// <param name="edits">The list of 1-based line numbers and their literal replacement text.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A confirmation message including the number of lines replaced, or a failure message.</returns>
    [Description("Replace lines in a file. Provide a list of edits, each with a 1-based line_number and a literal new_line (include your own trailing newline); an empty new_line deletes the line, including its line break. Fails on out-of-range or duplicate line numbers.")]
    private async Task<string> ReplaceLinesAsync(string fileName, List<FileLineEdit> edits, CancellationToken cancellationToken = default)
    {
        await this._writeLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            string path = StorePaths.NormalizeRelativePath(fileName);
            string? content = await this._fileStore.ReadAsync(path, cancellationToken).ConfigureAwait(false);
            if (content is null)
            {
                return $"File '{fileName}' not found.";
            }

            string newContent = FileEditor.ApplyReplaceLines(content, edits);
            await this._fileStore.WriteAsync(path, newContent, cancellationToken).ConfigureAwait(false);
            return $"Replaced {edits.Count} line(s) in '{fileName}'.";
        }
        finally
        {
            this._writeLock.Release();
        }
    }

    /// <summary>
    /// Search the contents of files in the store (recursively) using a regular expression pattern (case-insensitive).
    /// Optionally restrict to a base directory and/or filter which files to search using a glob pattern.
    /// </summary>
    /// <param name="regexPattern">A regular expression pattern to match against file contents (case-insensitive).</param>
    /// <param name="globPattern">An optional glob pattern to filter which files to search, matched against each file's path relative to the search directory. Leave empty or omit to search all files.</param>
    /// <param name="directory">An optional base directory (relative path) to restrict the search to. Leave empty or omit to search the whole store.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A list of search results whose file names are paths relative to the store root.</returns>
    [Description(
        """
        Search the contents of files in the store (recursively, across all subdirectories) using a regular expression pattern (case-insensitive).
        Optionally restrict the search to a base directory (relative path), and filter which files to search using a glob pattern matched against each file's path relative to that directory:
        - '*' matches within a single path segment
        - '**' matches across subdirectories, so use \"**/*.md\" to match markdown files at any depth, or \"reports/**\" to restrict the search to the 'reports' subtree.

        Returns matching results whose file names are paths relative to the store root (usable with file_access_read), along with snippets and matching lines with line numbers.
        """)]
    private async Task<List<FileSearchResult>> GrepAsync(string regexPattern, string? globPattern = null, string? directory = null, CancellationToken cancellationToken = default)
    {
        string? pattern = string.IsNullOrWhiteSpace(globPattern) ? null : globPattern;
        string target = StorePaths.NormalizeRelativePath(directory ?? string.Empty, isDirectory: true);
        IReadOnlyList<FileSearchResult> results = await this._fileStore.SearchAsync(target, regexPattern, pattern, recursive: true, cancellationToken).ConfigureAwait(false);

        // store.SearchAsync returns FileName relative to the searched directory; re-root each result to the
        // store root so the names compose directly with file_access_read/replace/delete.
        string prefix = target;
        if (prefix.Length == 0)
        {
            return new List<FileSearchResult>(results);
        }

        var rerooted = new List<FileSearchResult>(results.Count);
        foreach (FileSearchResult result in results)
        {
            rerooted.Add(new FileSearchResult
            {
                FileName = $"{prefix}/{result.FileName}",
                Snippet = result.Snippet,
                MatchingLines = result.MatchingLines,
            });
        }

        return rerooted;
    }

    private AITool[] CreateTools()
    {
        var serializerOptions = AgentJsonUtilities.DefaultOptions;

        // Read-only and store-modifying tools require approval by default. Approval can be disabled
        // per group via FileAccessProviderOptions.DisableReadOnlyToolApproval and DisableWriteToolApproval;
        // otherwise callers can use the ReadOnlyToolsAutoApprovalRule or AllToolsAutoApprovalRule with the
        // ToolApprovalAgent to automatically approve these tools.
        bool readOnlyRequiresApproval = !this._disableReadOnlyToolApproval;
        bool writeRequiresApproval = !this._disableWriteToolApproval;

        var tools = new List<AITool>
        {
            WrapWithApprovalIfRequired(AIFunctionFactory.Create(this.ReadAsync, new AIFunctionFactoryOptions { Name = ReadFileToolName, SerializerOptions = serializerOptions }), readOnlyRequiresApproval),
            WrapWithApprovalIfRequired(AIFunctionFactory.Create(this.LsAsync, new AIFunctionFactoryOptions { Name = LsToolName, SerializerOptions = serializerOptions }), readOnlyRequiresApproval),
            WrapWithApprovalIfRequired(AIFunctionFactory.Create(this.GrepAsync, new AIFunctionFactoryOptions { Name = GrepToolName, SerializerOptions = serializerOptions }), readOnlyRequiresApproval),
        };

        if (!this._disableWriteTools)
        {
            tools.Add(WrapWithApprovalIfRequired(AIFunctionFactory.Create(this.WriteAsync, new AIFunctionFactoryOptions { Name = WriteToolName, SerializerOptions = serializerOptions }), writeRequiresApproval));
            tools.Add(WrapWithApprovalIfRequired(AIFunctionFactory.Create(this.DeleteAsync, new AIFunctionFactoryOptions { Name = DeleteFileToolName, SerializerOptions = serializerOptions }), writeRequiresApproval));
            tools.Add(WrapWithApprovalIfRequired(AIFunctionFactory.Create(this.ReplaceAsync, new AIFunctionFactoryOptions { Name = ReplaceToolName, SerializerOptions = serializerOptions }), writeRequiresApproval));
            tools.Add(WrapWithApprovalIfRequired(AIFunctionFactory.Create(this.ReplaceLinesAsync, new AIFunctionFactoryOptions { Name = ReplaceLinesToolName, SerializerOptions = serializerOptions }), writeRequiresApproval));
        }

        return tools.ToArray();
    }

    private static AITool WrapWithApprovalIfRequired(AIFunction function, bool requireApproval)
        => requireApproval ? new ApprovalRequiredAIFunction(function) : function;
}
