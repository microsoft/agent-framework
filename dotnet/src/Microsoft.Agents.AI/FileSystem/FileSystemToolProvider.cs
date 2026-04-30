// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A high-fidelity, filesystem-specific <see cref="FileAccessProvider"/> that exposes both the universal
/// file-access tools and a richer coding-workspace tool surface (line-range view, atomic edits,
/// gitignore-aware glob/grep, recursive directory listing, approval-gated mutations).
/// </summary>
/// <remarks>
/// <para>
/// Use <see cref="FileSystemToolProvider"/> when an agent operates on a real filesystem workspace
/// and benefits from line-precise reads, unique-match edits, atomic batched edits, ripgrep-backed
/// content search, and gitignore-aware discovery. Destructive operations are gated through
/// <see cref="ApprovalRequiredAIFunction"/> so harness components such as <c>ToolApprovalAgent</c>
/// can prompt the user or apply standing approval rules before they execute.
/// </para>
/// <para>
/// For agents that need a pluggable backend (in-memory, remote storage, etc.) or a simpler shared-folder
/// vocabulary, prefer the base <see cref="FileAccessProvider"/> with the appropriate <see cref="AgentFileStore"/>.
/// </para>
/// <para>
/// Because <see cref="FileSystemToolProvider"/> derives from <see cref="FileAccessProvider"/>, it can be
/// used wherever a <see cref="FileAccessProvider"/> is accepted. The universal tool names
/// (<c>FileAccess_SaveFile</c>, <c>FileAccess_ReadFile</c>, etc.) remain identical so agent prompts and
/// downstream code do not need to change vocabulary.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileSystemToolProvider : FileAccessProvider
{
    private const string CodingWorkspaceInstructions =
        """
        ## File Access
        You have a sandboxed working directory exposed via two complementary tool surfaces:

        Universal file tools (`FileAccess_*`) — for simple whole-file reads, writes, deletes, listings, and content search:
        - `FileAccess_SaveFile`, `FileAccess_ReadFile`, `FileAccess_DeleteFile`, `FileAccess_ListFiles`, `FileAccess_SearchFiles`.

        High-fidelity coding tools (`fs_*`) — preferred for editing source code, navigating a tree, and searching by line:
        - `fs_view` — read with optional 1-based line range.
        - `fs_edit` — replace exactly N occurrences of a unique substring.
        - `fs_multi_edit` — apply many edits atomically (all-or-nothing).
        - `fs_glob` — discover files by glob pattern.
        - `fs_grep` — regex line search across files (uses ripgrep when available).
        - `fs_list_dir` — recursive listing with bounded depth.
        - `fs_move`, `fs_rename` — relocate files (will request approval before executing).
        - `FileAccess_DeleteFile` — also requests approval through this provider.

        Guidelines:
        - Prefer `fs_view` + `fs_edit`/`fs_multi_edit` when modifying existing files, to keep diffs minimal.
        - Prefer `fs_grep` and `fs_glob` over reading whole directories when looking for specific content.
        - Never delete or overwrite files outside what the user has explicitly asked you to change.
        - Paths are sandboxed under the working directory. Symlinks, secrets-like paths, and gitignored entries are filtered for safety.
        """;

    private readonly FileSystemTool _fsTool;

    /// <summary>
    /// Initializes a new instance of the <see cref="FileSystemToolProvider"/> class rooted at <paramref name="rootDirectory"/>.
    /// </summary>
    /// <param name="rootDirectory">
    /// The absolute or relative path to the working directory the agent may operate within. Created if it does not exist.
    /// All file paths supplied to inherited or added tools are resolved relative to this root.
    /// </param>
    /// <param name="options">Optional settings. When <see langword="null"/>, secure defaults are used.</param>
    public FileSystemToolProvider(string rootDirectory, FileSystemToolProviderOptions? options = null)
        : base(
            new FileSystemAgentFileStore(
                Throw.IfNullOrWhitespace(rootDirectory),
                BuildStoreOptions(options)),
            BuildAccessOptions(options))
    {
        Directory.CreateDirectory(rootDirectory);
        this.Root = Path.GetFullPath(rootDirectory);
        this._fsTool = new FileSystemTool(this.Root, options?.Policy);
    }

    /// <summary>
    /// Gets the resolved absolute root directory of the workspace.
    /// </summary>
    public string Root { get; }

    /// <inheritdoc />
    protected override string DefaultInstructions => CodingWorkspaceInstructions;

    /// <inheritdoc />
    protected override AITool[] CreateTools()
    {
        AITool[] baseTools = base.CreateTools();

        // Wrap the inherited DeleteFile tool with an approval gate so it is consistent with the
        // approval-gated rich mutations (fs_move, fs_rename).
        for (int i = 0; i < baseTools.Length; i++)
        {
            if (baseTools[i] is AIFunction f &&
                f.Name == "FileAccess_DeleteFile")
            {
                baseTools[i] = new ApprovalRequiredAIFunction(f);
            }
        }

        // Append the high-fidelity tools, omitting any that exactly duplicate a universal tool's
        // semantics (fs_create -> FileAccess_SaveFile; fs_delete -> FileAccess_DeleteFile).
        var richTools = new List<AITool>();
        foreach (AITool tool in this._fsTool.AsTools())
        {
            string? name = (tool as AIFunction)?.Name;

            if (name is "fs_create" or "fs_delete")
            {
                continue;
            }

            richTools.Add(tool);
        }

        var combined = new AITool[baseTools.Length + richTools.Count];
        baseTools.CopyTo(combined, 0);
        richTools.CopyTo(combined, baseTools.Length);
        return combined;
    }

    private static FileSystemAgentFileStoreOptions BuildStoreOptions(FileSystemToolProviderOptions? options) => new()
    {
        RejectSymlinks = options?.RejectSymlinks ?? true,
        // Default to FileSystemPolicy.DefaultDenylist so the universal tools enforce the same secrets
        // protection the rich tools do. Callers can pass an empty list to opt out.
        Denylist = options?.StoreDenylist ?? FileSystemPolicy.DefaultDenylist,
    };

    private static FileAccessProviderOptions? BuildAccessOptions(FileSystemToolProviderOptions? options) =>
        options?.Instructions is null
            ? null
            : new FileAccessProviderOptions { Instructions = options.Instructions };
}
