// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// An <see cref="AIContextProvider"/> that provides file-based memory tools to an agent
/// for storing, retrieving, modifying, listing, deleting, and searching files.
/// </summary>
/// <remarks>
/// <para>
/// The <see cref="FileMemoryProvider"/> enables agents to persist information across interactions
/// using a file-based storage model. Each memory is stored as an individual file with a meaningful name.
/// For large files, a companion description file (suffixed with <c>_description.md</c>) can be stored
/// alongside the main file to provide a summary.
/// </para>
/// <para>
/// File access is mediated through a <see cref="AgentFileStore"/> abstraction, allowing pluggable
/// backends (in-memory, local file system, remote blob storage, etc.).
/// </para>
/// <para>
/// This provider exposes the following tools to the agent:
/// <list type="bullet">
/// <item><description><c>SaveFile</c> — Save a memory file with the given name, content, and an optional description.</description></item>
/// <item><description><c>ReadFile</c> — Read the content of a file by name.</description></item>
/// <item><description><c>DeleteFile</c> — Delete a file by name.</description></item>
/// <item><description><c>ListFiles</c> — List all files with their descriptions (if available).</description></item>
/// <item><description><c>SearchFiles</c> — Search file contents using a regular expression pattern.</description></item>
/// </list>
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileMemoryProvider : AIContextProvider, IDisposable
{
    private const string DescriptionSuffix = "_description.md";
    private const string MemoryIndexFileName = "memories.md";
    private const int MaxIndexEntries = 50;

    private const string DefaultInstructions =
        """
        ## File Based Memory
        You have access to a session-scoped, file-based memory system via the `FileMemory_*` tools for storing and retrieving information across interactions.
        These files act as your working memory for the current session and are isolated from other sessions.
        Use these tools to store plans, memories, processing results, or downloaded data.

        - Use descriptive file names (e.g., "projectarchitecture.md", "userpreferences.md").
        - Include a description when saving a file to help with future discovery.
        - Before starting new tasks, use FileMemory_ListFiles and FileMemory_SearchFiles to check for relevant existing memories.
        - Keep memories up-to-date by overwriting files when information changes.
        - When you receive large amounts of data (e.g., downloaded web pages, API responses, research results),
          save them to files if they will be required later, so that they are not lost when older context is compacted or truncated.
          This ensures important data remains accessible across long-running sessions.
        """;

    private readonly AgentFileStore _fileStore;
    private readonly ProviderSessionState<FileMemoryState> _sessionState;
    private readonly SemaphoreSlim _writeLock = new(1, 1);
    private readonly string _instructions;
    private IReadOnlyList<string>? _stateKeys;
    private AITool[]? _tools;

    /// <summary>
    /// Initializes a new instance of the <see cref="FileMemoryProvider"/> class.
    /// </summary>
    /// <param name="fileStore">The file store implementation used for storage operations.</param>
    /// <param name="stateInitializer">
    /// An optional function that initializes the <see cref="FileMemoryState"/> for a new session.
    /// Use this to customize the working folder (e.g., per-user or per-session subfolders).
    /// When <see langword="null"/>, the default initializer creates state with an empty working folder.
    /// </param>
    /// <param name="options">Optional settings that control provider behavior. When <see langword="null"/>, defaults are used.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="fileStore"/> is <see langword="null"/>.</exception>
    public FileMemoryProvider(AgentFileStore fileStore, Func<AgentSession?, FileMemoryState>? stateInitializer = null, FileMemoryProviderOptions? options = null)
    {
        Throw.IfNull(fileStore);

        this._fileStore = fileStore;
        this._instructions = options?.Instructions ?? DefaultInstructions;
        this._sessionState = new ProviderSessionState<FileMemoryState>(
            stateInitializer ?? (_ => new FileMemoryState()),
            this.GetType().Name,
            AgentJsonUtilities.DefaultOptions);
    }

    /// <inheritdoc />
    public override IReadOnlyList<string> StateKeys => this._stateKeys ??= [this._sessionState.StateKey];

    /// <summary>
    /// Releases the resources used by the <see cref="FileMemoryProvider"/>.
    /// </summary>
    public void Dispose()
    {
        this._writeLock.Dispose();
    }

    /// <inheritdoc />
    protected override async ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        FileMemoryState state = this._sessionState.GetOrInitializeState(context.Session);

        // Ensure the working folder exists in the store.
        if (!string.IsNullOrEmpty(state.WorkingFolder))
        {
            await this._fileStore.CreateDirectoryAsync(state.WorkingFolder, cancellationToken).ConfigureAwait(false);
        }

        var aiContext = new AIContext
        {
            Instructions = this._instructions,
            Tools = this._tools ??= this.CreateTools(),
        };

        // Inject the memory index as a user message so the agent knows what memories are available.
        string indexPath = CombinePaths(state.WorkingFolder, MemoryIndexFileName);
        string? indexContent = await this._fileStore.ReadFileAsync(indexPath, cancellationToken).ConfigureAwait(false);
        if (!string.IsNullOrWhiteSpace(indexContent))
        {
            aiContext.Messages =
            [
                new ChatMessage(ChatRole.User,
                    "The following is your memory index — a list of files you have previously saved. " +
                    "You can read any of these files using the FileMemory_ReadFile tool.\n\n" +
                    indexContent),
            ];
        }

        return aiContext;
    }

    /// <summary>
    /// Save a memory file with the given name and content.
    /// Overwrites the file if it already exists.
    /// Include a description for large files to provide a summary that helps with discovery.
    /// </summary>
    /// <param name="fileName">The name of the file to save.</param>
    /// <param name="content">The content to write to the file.</param>
    /// <param name="description">An optional description of the file contents for discovery. Leave empty or omit to skip.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A confirmation message.</returns>
    [Description("Save a memory file with the given name and content. Overwrites the file if it already exists. Include a description for large files to provide a summary that helps with discovery.")]
    private async Task<string> SaveFileAsync(string fileName, string content, string? description = null, CancellationToken cancellationToken = default)
    {
        if (IsInternalFile(fileName))
        {
            throw new ArgumentException("The provided file name is reserved by the system for internal use. Please choose a different file name.", nameof(fileName));
        }

        FileMemoryState state = this._sessionState.GetOrInitializeState(AIAgent.CurrentRunContext?.Session);
        string path = ResolvePath(state.WorkingFolder, fileName);

        await this._writeLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            await this._fileStore.WriteFileAsync(path, content, cancellationToken).ConfigureAwait(false);

            string descPath = ResolvePath(state.WorkingFolder, GetDescriptionFileName(fileName));

            if (!string.IsNullOrWhiteSpace(description))
            {
                await this._fileStore.WriteFileAsync(descPath, description, cancellationToken).ConfigureAwait(false);
            }
            else
            {
                // Remove any stale description file when no description is provided.
                await this._fileStore.DeleteFileAsync(descPath, cancellationToken).ConfigureAwait(false);
            }

            string result = string.IsNullOrWhiteSpace(description)
                ? $"File '{fileName}' saved."
                : $"File '{fileName}' saved with description.";

            await this.RebuildMemoryIndexAsync(state, cancellationToken).ConfigureAwait(false);
            return result;
        }
        finally
        {
            this._writeLock.Release();
        }
    }

    /// <summary>
    /// Read the content of a memory file by name.
    /// Returns the file content or a message indicating the file was not found.
    /// </summary>
    /// <param name="fileName">The name of the file to read.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>The file content or a not-found message.</returns>
    [Description("Read the content of a memory file by name. Returns the file content or a message indicating the file was not found.")]
    private async Task<string> ReadFileAsync(string fileName, CancellationToken cancellationToken = default)
    {
        FileMemoryState state = this._sessionState.GetOrInitializeState(AIAgent.CurrentRunContext?.Session);
        string path = ResolvePath(state.WorkingFolder, fileName);
        string? content = await this._fileStore.ReadFileAsync(path, cancellationToken).ConfigureAwait(false);
        return content ?? $"File '{fileName}' not found.";
    }

    /// <summary>
    /// Delete a memory file by name. Also removes its companion description file if one exists.
    /// </summary>
    /// <param name="fileName">The name of the file to delete.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A confirmation or not-found message.</returns>
    [Description("Delete a memory file by name. Also removes its companion description file if one exists.")]
    private async Task<string> DeleteFileAsync(string fileName, CancellationToken cancellationToken = default)
    {
        FileMemoryState state = this._sessionState.GetOrInitializeState(AIAgent.CurrentRunContext?.Session);
        string path = ResolvePath(state.WorkingFolder, fileName);

        await this._writeLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            bool deleted = await this._fileStore.DeleteFileAsync(path, cancellationToken).ConfigureAwait(false);

            // Also delete companion description file if it exists.
            string descPath = ResolvePath(state.WorkingFolder, GetDescriptionFileName(fileName));
            await this._fileStore.DeleteFileAsync(descPath, cancellationToken).ConfigureAwait(false);

            await this.RebuildMemoryIndexAsync(state, cancellationToken).ConfigureAwait(false);
            return deleted ? $"File '{fileName}' deleted." : $"File '{fileName}' not found.";
        }
        finally
        {
            this._writeLock.Release();
        }
    }

    /// <summary>
    /// List all memory files with their descriptions (if available). Description files are not shown separately.
    /// </summary>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A list of file entries with names and optional descriptions.</returns>
    [Description("List all memory files with their descriptions (if available). Description files are not shown separately.")]
    private async Task<List<FileListEntry>> ListFilesAsync(CancellationToken cancellationToken = default)
    {
        FileMemoryState state = this._sessionState.GetOrInitializeState(AIAgent.CurrentRunContext?.Session);
        IReadOnlyList<string> fileNames = await this._fileStore.ListFilesAsync(state.WorkingFolder, cancellationToken).ConfigureAwait(false);

        var descriptionFileSet = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string file in fileNames)
        {
            if (file.EndsWith(DescriptionSuffix, StringComparison.OrdinalIgnoreCase))
            {
                descriptionFileSet.Add(file);
            }
        }

        var entries = new List<FileListEntry>();
        foreach (string file in fileNames)
        {
            if (descriptionFileSet.Contains(file))
            {
                continue;
            }

            if (IsInternalFile(file))
            {
                continue;
            }

            string? fileDescription = null;
            string descFileName = GetDescriptionFileName(file);

            if (descriptionFileSet.Contains(descFileName))
            {
                string descPath = CombinePaths(state.WorkingFolder, descFileName);
                fileDescription = await this._fileStore.ReadFileAsync(descPath, cancellationToken).ConfigureAwait(false);
            }

            entries.Add(new FileListEntry { FileName = file, Description = fileDescription });
        }

        return entries;
    }

    /// <summary>
    /// Search memory file contents using a regular expression pattern (case-insensitive).
    /// Optionally filter which files to search using a glob pattern.
    /// Returns matching file names, content snippets, and matching lines with line numbers.
    /// </summary>
    /// <param name="regexPattern">A regular expression pattern to match against file contents (case-insensitive).</param>
    /// <param name="filePattern">An optional glob pattern to filter which files to search (e.g., "*.md", "research*"). Leave empty or omit to search all files.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A list of search results with matching file names, snippets, and matching lines.</returns>
    [Description("Search memory file contents using a regular expression pattern (case-insensitive). Optionally filter which files to search using a glob pattern (e.g., \"*.md\", \"research*\"). Returns matching file names, content snippets, and matching lines with line numbers.")]
    private async Task<List<FileSearchResult>> SearchFilesAsync(string regexPattern, string? filePattern = null, CancellationToken cancellationToken = default)
    {
        FileMemoryState state = this._sessionState.GetOrInitializeState(AIAgent.CurrentRunContext?.Session);
        string? pattern = string.IsNullOrWhiteSpace(filePattern) ? null : filePattern;
        IReadOnlyList<FileSearchResult> results = await this._fileStore.SearchFilesAsync(state.WorkingFolder, regexPattern, pattern, cancellationToken).ConfigureAwait(false);

        // Filter out internal files (description sidecars and memory index) so they stay hidden.
        var filtered = new List<FileSearchResult>(results.Count);
        foreach (var result in results)
        {
            if (IsInternalFile(result.FileName))
            {
                continue;
            }

            filtered.Add(result);
        }

        return filtered;
    }

    private AITool[] CreateTools()
    {
        var serializerOptions = AgentJsonUtilities.DefaultOptions;

        return
        [
            AIFunctionFactory.Create(this.SaveFileAsync, new AIFunctionFactoryOptions { Name = "FileMemory_SaveFile", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.ReadFileAsync, new AIFunctionFactoryOptions { Name = "FileMemory_ReadFile", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.DeleteFileAsync, new AIFunctionFactoryOptions { Name = "FileMemory_DeleteFile", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.ListFilesAsync, new AIFunctionFactoryOptions { Name = "FileMemory_ListFiles", SerializerOptions = serializerOptions }),
            AIFunctionFactory.Create(this.SearchFilesAsync, new AIFunctionFactoryOptions { Name = "FileMemory_SearchFiles", SerializerOptions = serializerOptions }),
        ];
    }

    /// <summary>
    /// Rebuilds the <c>memories.md</c> index file by listing all user files in the working folder,
    /// reading their companion description files, and writing a markdown summary capped at <see cref="MaxIndexEntries"/> entries.
    /// </summary>
    private async Task RebuildMemoryIndexAsync(FileMemoryState state, CancellationToken cancellationToken)
    {
        IReadOnlyList<string> fileNames = await this._fileStore.ListFilesAsync(state.WorkingFolder, cancellationToken).ConfigureAwait(false);

        // Sort deterministically so the index is stable across runs and platforms.
        var sortedFiles = fileNames.OrderBy(f => f, StringComparer.OrdinalIgnoreCase).ToList();

        var sb = new System.Text.StringBuilder();
        sb.AppendLine("# Memory Index");
        sb.AppendLine();

        int count = 0;
        foreach (string file in sortedFiles)
        {
            // Skip internal system files.
            if (IsInternalFile(file))
            {
                continue;
            }

            if (count >= MaxIndexEntries)
            {
                break;
            }

            string? description = null;
            string descFileName = GetDescriptionFileName(file);
            string descPath = CombinePaths(state.WorkingFolder, descFileName);
            description = await this._fileStore.ReadFileAsync(descPath, cancellationToken).ConfigureAwait(false);

            if (!string.IsNullOrWhiteSpace(description))
            {
                sb.AppendLine($"- **{file}**: {description}");
            }
            else
            {
                sb.AppendLine($"- **{file}**");
            }

            count++;
        }

        string indexPath = CombinePaths(state.WorkingFolder, MemoryIndexFileName);
        await this._fileStore.WriteFileAsync(indexPath, sb.ToString(), cancellationToken).ConfigureAwait(false);
    }

    private static string GetDescriptionFileName(string fileName)
    {
        int extIndex = fileName.LastIndexOf('.');
        if (extIndex > 0)
        {
#pragma warning disable CA1845 // Use span-based 'string.Concat' — not available on all target frameworks
            return fileName.Substring(0, extIndex) + DescriptionSuffix;
#pragma warning restore CA1845
        }

        return fileName + DescriptionSuffix;
    }

    /// <summary>
    /// Returns <see langword="true"/> if the file is an internal system file that should be hidden
    /// from user-facing operations (description sidecars and the memory index).
    /// </summary>
    private static bool IsInternalFile(string fileName) =>
        fileName.EndsWith(DescriptionSuffix, StringComparison.OrdinalIgnoreCase) ||
        fileName.Equals(MemoryIndexFileName, StringComparison.OrdinalIgnoreCase);

    private static string ResolvePath(string workingFolder, string fileName)
    {
        // Validate and normalize the file name (rejects rooted, traversal, empty, etc.).
        // Only fileName needs validation — workingFolder is developer-provided and trusted.
        string normalizedFileName = StorePaths.NormalizeRelativePath(fileName);

        string normalizedWorkingFolder = workingFolder.Replace('\\', '/');
        return CombinePaths(normalizedWorkingFolder, normalizedFileName);
    }

    private static string CombinePaths(string basePath, string relativePath)
    {
        if (string.IsNullOrEmpty(basePath))
        {
            return relativePath;
        }

        if (string.IsNullOrEmpty(relativePath))
        {
            return basePath;
        }

        return basePath.TrimEnd('/') + "/" + relativePath.TrimStart('/');
    }
}
