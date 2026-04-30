// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>Security policy controlling <see cref="FileSystemTool"/> operations.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed record FileSystemPolicy
{
    /// <summary>Default denylist patterns.</summary>
    public static readonly IReadOnlyList<string> DefaultDenylist =
    [
        ".git/**", "**/.git/**", ".env*", "**/.env*", "*.pem", "**/*.pem", "*.key", "**/*.key",
        "id_rsa*", "**/id_rsa*", "id_ed25519*", "**/id_ed25519*", ".ssh/**", "**/.ssh/**",
        ".aws/credentials", "**/.aws/credentials", ".npmrc", "**/.npmrc", ".pypirc", "**/.pypirc", ".netrc", "**/.netrc",
    ];

    /// <summary>Gets readable path allowlist patterns, or <see langword="null"/> to allow reads anywhere under root.</summary>
    public IReadOnlyList<string>? ReadPaths { get; init; }

    /// <summary>Gets writable path allowlist patterns, or <see langword="null"/> to allow writes anywhere under root.</summary>
    public IReadOnlyList<string>? WritePaths { get; init; }

    /// <summary>Gets denylist patterns that always block access.</summary>
    public IReadOnlyList<string> Denylist { get; init; } = DefaultDenylist;

    /// <summary>Gets the maximum file size in bytes.</summary>
    public int MaxFileBytes { get; init; } = 5 * 1024 * 1024;

    /// <summary>Gets the maximum number of discovery results.</summary>
    public int MaxResults { get; init; } = 1000;

    /// <summary>Gets the maximum number of lines returned by view.</summary>
    public int MaxViewLines { get; init; } = 2000;

    /// <summary>Gets a value indicating whether grep may use ripgrep.</summary>
    public bool AllowGrepRipgrep { get; init; } = true;

    /// <summary>Gets a value indicating whether discovery respects .gitignore files.</summary>
    public bool RespectGitignore { get; init; } = true;
}

/// <summary>Raised when an operation is blocked by sandbox or policy.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public class FileSystemSecurityException : UnauthorizedAccessException
{
    /// <summary>Initializes a new instance of the <see cref="FileSystemSecurityException"/> class.</summary>
    public FileSystemSecurityException() { }

    /// <summary>Initializes a new instance of the <see cref="FileSystemSecurityException"/> class.</summary>
    public FileSystemSecurityException(string message) : base(message) { }

    /// <summary>Initializes a new instance of the <see cref="FileSystemSecurityException"/> class.</summary>
    public FileSystemSecurityException(string message, Exception innerException) : base(message, innerException) { }
}

/// <summary>Result returned by <see cref="FileSystemTool.View"/>.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed record ViewResult(
    [property: JsonPropertyName("path")] string Path,
    [property: JsonPropertyName("content")] string Content,
    [property: JsonPropertyName("start_line")] int StartLine,
    [property: JsonPropertyName("end_line")] int EndLine,
    [property: JsonPropertyName("total_lines")] int TotalLines,
    [property: JsonPropertyName("truncated")] bool Truncated);

/// <summary>Result returned by <see cref="FileSystemTool.Create"/>.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed record CreateResult(
    [property: JsonPropertyName("path")] string Path,
    [property: JsonPropertyName("bytes_written")] int BytesWritten);

/// <summary>Result returned by <see cref="FileSystemTool.Edit"/>.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed record EditResult(
    [property: JsonPropertyName("path")] string Path,
    [property: JsonPropertyName("replacements")] int Replacements,
    [property: JsonPropertyName("bytes_written")] int BytesWritten);

/// <summary>An operation supplied to <see cref="FileSystemTool.MultiEdit"/>.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed record MultiEditOperation(
    [property: JsonPropertyName("old_str")] string OldStr,
    [property: JsonPropertyName("new_str")] string NewStr,
    [property: JsonPropertyName("count")] int Count = 1);

/// <summary>Result returned by <see cref="FileSystemTool.MultiEdit"/>.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed record MultiEditResult(
    [property: JsonPropertyName("path")] string Path,
    [property: JsonPropertyName("edits_applied")] int EditsApplied,
    [property: JsonPropertyName("total_replacements")] int TotalReplacements,
    [property: JsonPropertyName("bytes_written")] int BytesWritten);

/// <summary>Result returned by <see cref="FileSystemTool.Glob"/>.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed record GlobResult(
    [property: JsonPropertyName("matches")] IReadOnlyList<string> Matches,
    [property: JsonPropertyName("truncated")] bool Truncated);

/// <summary>Result returned by <see cref="FileSystemTool.Grep"/>.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed record GrepResult(
    [property: JsonPropertyName("hits")] IReadOnlyList<GrepResult.GrepHit> Hits,
    [property: JsonPropertyName("truncated")] bool Truncated,
    [property: JsonPropertyName("backend")] string Backend)
{
    /// <summary>A single grep hit.</summary>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public sealed record GrepHit(
        [property: JsonPropertyName("path")] string Path,
        [property: JsonPropertyName("line_number")] int LineNumber,
        [property: JsonPropertyName("line")] string Line);
}

/// <summary>Result returned by <see cref="FileSystemTool.ListDir"/>.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed record ListDirResult(
    [property: JsonPropertyName("path")] string Path,
    [property: JsonPropertyName("entries")] IReadOnlyList<ListDirResult.DirEntry> Entries,
    [property: JsonPropertyName("truncated")] bool Truncated)
{
    /// <summary>A directory entry.</summary>
    [Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
    public sealed record DirEntry(
        [property: JsonPropertyName("path")] string Path,
        [property: JsonPropertyName("type")] string Type,
        [property: JsonPropertyName("size")] long? Size);
}

/// <summary>Result returned by <see cref="FileSystemTool.Delete"/>.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed record DeleteResult(
    [property: JsonPropertyName("path")] string Path);

/// <summary>Result returned by move operations.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed record MoveResult(
    [property: JsonPropertyName("source")] string Source,
    [property: JsonPropertyName("destination")] string Destination);

/// <summary>Sandboxed filesystem operations exposed as agent tools.</summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileSystemTool
{
    private const int DefaultListDepth = 1;
    private const int DefaultMaxListDepth = 20;
    private readonly FileSystemPolicy _policy;
    private readonly string? _rgPath;
    private GitignoreMatcher? _gitignore;

    /// <summary>Initializes a new instance of the <see cref="FileSystemTool"/> class.</summary>
    public FileSystemTool(string root, FileSystemPolicy? policy = null)
    {
        if (!Directory.Exists(root))
        {
            throw new ArgumentException($"FileSystemTool root does not exist or is not a directory: {root}", nameof(root));
        }

        this.Root = Path.GetFullPath(root);
        this._policy = policy ?? new FileSystemPolicy();
        this._rgPath = FindOnPath("rg") ?? FindOnPath("rg.exe");
    }

    /// <summary>Gets the resolved absolute root directory.</summary>
    public string Root { get; }

    /// <summary>Returns this tool as AI-callable filesystem functions.</summary>
    public IList<AITool> AsTools() =>
    [
        this.CreateTool("fs_view", nameof(this.View)),
        this.CreateTool("fs_create", nameof(this.Create)),
        this.CreateTool("fs_edit", nameof(this.Edit)),
        this.CreateTool("fs_multi_edit", nameof(this.MultiEditTool), nonPublic: true),
        this.CreateTool("fs_glob", nameof(this.Glob)),
        this.CreateTool("fs_grep", nameof(this.Grep)),
        this.CreateTool("fs_list_dir", nameof(this.ListDir)),
        new ApprovalRequiredAIFunction(this.CreateTool("fs_delete", nameof(this.Delete))),
        new ApprovalRequiredAIFunction(this.CreateTool("fs_move", nameof(this.Move))),
        new ApprovalRequiredAIFunction(this.CreateTool("fs_rename", nameof(this.Rename))),
    ];

    [Description("Apply multiple text replacements atomically.")]
    private MultiEditResult MultiEditTool([Description("Path to edit.")] string path, [Description("Sequential edit operations.")] List<MultiEditOperation> edits)
        => this.MultiEdit(path, edits);

    private AIFunction CreateTool(string name, string methodName, bool nonPublic = false)
    {
        BindingFlags flags = BindingFlags.Instance | (nonPublic ? BindingFlags.NonPublic : BindingFlags.Public);
        MethodInfo method = typeof(FileSystemTool).GetMethod(methodName, flags) ?? throw new InvalidOperationException($"Missing method: {methodName}");
        var options = new AIFunctionFactoryOptions { Name = name, SerializerOptions = AgentJsonUtilities.DefaultOptions };
        return AIFunctionFactory.Create(method, this, options);
    }
    /// <summary>Reads a UTF-8 text file.</summary>
    [Description("Read a UTF-8 text file from the sandbox.")]
    public ViewResult View([Description("Path to read, relative to root.")] string path, [Description("Optional 1-based start line.")] int? startLine = null, [Description("Optional 1-based end line.")] int? endLine = null)
    {
        string full = this.ResolveInRoot(path);
        string rel = this.RelativePosix(full);
        this.CheckReadAllowed(rel);
        EnsureFile(full);
        string text = this.ReadText(full);
        string[] lines = SplitLines(text);
        int total = lines.Length;
        int start = startLine ?? 1;
        int end = endLine ?? Math.Min(total, start + this._policy.MaxViewLines - 1);
        if (start < 1 || end < start)
        {
            throw new ArgumentException("Invalid line range.");
        }

        int cappedEnd = Math.Min(end, Math.Min(total, start + this._policy.MaxViewLines - 1));
        string content = string.Join(Environment.NewLine, lines.Skip(start - 1).Take(Math.Max(0, cappedEnd - start + 1)));
        return new ViewResult(rel, content, start, cappedEnd, total, cappedEnd < end || cappedEnd < total);
    }

    /// <summary>Creates a new UTF-8 text file.</summary>
    [Description("Create a new UTF-8 text file in the sandbox.")]
    public CreateResult Create([Description("Path to create, relative to root.")] string path, [Description("UTF-8 text content.")] string content)
    {
        string full = this.ResolveInRoot(path, allowMissingLeaf: true);
        string rel = this.RelativePosix(full);
        this.CheckWriteAllowed(rel);
        if (File.Exists(full) || Directory.Exists(full))
        {
            throw new IOException($"Path already exists: {rel}");
        }

        byte[] bytes = s_strictUtf8.GetBytes(content);
        this.EnsureWithinMaxBytes(bytes.Length);
        AtomicWriteBytes(full, bytes);
        return new CreateResult(rel, bytes.Length);
    }

    /// <summary>Edits a UTF-8 text file.</summary>
    [Description("Replace text in a UTF-8 file.")]
    public EditResult Edit([Description("Path to edit.")] string path, [Description("Exact old string.")] string oldStr, [Description("Replacement string.")] string newStr, [Description("Required replacement count.")] int count = 1)
    {
        if (string.IsNullOrEmpty(oldStr)) { throw new ArgumentException("old_str must not be empty.", nameof(oldStr)); }
        if (count < 1) { throw new ArgumentOutOfRangeException(nameof(count), "count must be positive."); }
        string full = this.ResolveInRoot(path);
        string rel = this.RelativePosix(full);
        this.CheckReadAllowed(rel); this.CheckWriteAllowed(rel); EnsureFile(full);
        string text = this.ReadText(full);
        int found = CountOccurrences(text, oldStr);
        if (found != count) { throw new InvalidOperationException($"Expected {count} occurrence(s), found {found}."); }
        string updated = ReplaceExact(text, oldStr, newStr, count);
        byte[] bytes = s_strictUtf8.GetBytes(updated);
        this.EnsureWithinMaxBytes(bytes.Length);
        AtomicWriteBytes(full, bytes);
        return new EditResult(rel, count, bytes.Length);
    }

    /// <summary>Applies multiple edits atomically.</summary>
    [Description("Apply multiple text replacements atomically.")]
    public MultiEditResult MultiEdit([Description("Path to edit.")] string path, [Description("Sequential edit operations.")] IList<MultiEditOperation> edits)
    {
        if (edits is null || edits.Count == 0) { throw new ArgumentException("edits must not be empty.", nameof(edits)); }
        string full = this.ResolveInRoot(path);
        string rel = this.RelativePosix(full);
        this.CheckReadAllowed(rel); this.CheckWriteAllowed(rel); EnsureFile(full);
        string text = this.ReadText(full);
        int total = 0;
        foreach (MultiEditOperation edit in edits)
        {
            if (string.IsNullOrEmpty(edit.OldStr)) { throw new ArgumentException("old_str must not be empty.", nameof(edits)); }
            if (edit.Count < 1) { throw new ArgumentOutOfRangeException(nameof(edits), "count must be positive."); }
            int found = CountOccurrences(text, edit.OldStr);
            if (found != edit.Count) { throw new InvalidOperationException($"Expected {edit.Count} occurrence(s), found {found}."); }
            text = ReplaceExact(text, edit.OldStr, edit.NewStr, edit.Count);
            total += edit.Count;
        }

        byte[] bytes = s_strictUtf8.GetBytes(text);
        this.EnsureWithinMaxBytes(bytes.Length);
        AtomicWriteBytes(full, bytes);
        return new MultiEditResult(rel, edits.Count, total, bytes.Length);
    }

    /// <summary>Finds files by glob.</summary>
    [Description("Find files by glob pattern.")]
    public GlobResult Glob([Description("Glob pattern.")] string pattern, [Description("Optional scoped search path.")] string? path = null)
    {
        if (string.IsNullOrWhiteSpace(pattern)) { throw new ArgumentException("pattern must not be empty.", nameof(pattern)); }
        string basePath = this.ResolveInRoot(path ?? ".");
        if (!Directory.Exists(basePath)) { throw new DirectoryNotFoundException(path); }
        var matches = new List<string>();
        foreach (string file in SafeWalkFiles(basePath, this.Root, this._policy.Denylist, this.GetGitignore()))
        {
            string rel = this.RelativePosix(file);
            if (MatchGlob(rel, pattern) || MatchGlob(RelativePosix(basePath, file), pattern))
            {
                this.CheckReadAllowed(rel);
                matches.Add(rel);
                if (matches.Count >= this._policy.MaxResults) { return new GlobResult(matches.OrderBy(x => x, StringComparer.Ordinal).ToList(), true); }
            }
        }
        return new GlobResult(matches.OrderBy(x => x, StringComparer.Ordinal).ToList(), false);
    }

    /// <summary>Searches files by regex.</summary>
    [Description("Search UTF-8 text files by regular expression.")]
    public GrepResult Grep([Description("Regular expression pattern.")] string pattern, [Description("Whether matching ignores case.")] bool ignoreCase = false, [Description("Optional file glob filter.")] string? include = null)
    {
        if (this._policy.AllowGrepRipgrep && this._rgPath is not null)
        {
            try { return this.GrepRipgrep(pattern, ignoreCase, include); } catch (Exception ex) when (ex is IOException or InvalidOperationException) { }
        }
        return this.GrepDotNet(pattern, ignoreCase, include);
    }

    /// <summary>Lists files and directories.</summary>
    [Description("List files and directories.")]
    public ListDirResult ListDir([Description("Directory path.")] string path = ".", [Description("Maximum depth.")] int depth = DefaultListDepth)
    {
        string basePath = this.ResolveInRoot(path);
        string relBase = this.RelativePosix(basePath);
        this.CheckReadAllowed(string.IsNullOrEmpty(relBase) ? "." : relBase);
        if (!Directory.Exists(basePath)) { throw new DirectoryNotFoundException(path); }
        depth = Math.Max(0, Math.Min(depth, DefaultMaxListDepth));
        var entries = new List<ListDirResult.DirEntry>();
        foreach ((string entry, bool isDir) in WalkWithDepth(basePath, this.Root, this._policy.Denylist, depth, this.GetGitignore()))
        {
            string rel = this.RelativePosix(entry);
            this.CheckReadAllowed(rel);
            entries.Add(new ListDirResult.DirEntry(rel, isDir ? "directory" : "file", isDir ? null : new FileInfo(entry).Length));
            if (entries.Count >= this._policy.MaxResults) { return new ListDirResult(relBase, entries.OrderBy(e => e.Path, StringComparer.Ordinal).ToList(), true); }
        }
        return new ListDirResult(relBase, entries.OrderBy(e => e.Path, StringComparer.Ordinal).ToList(), false);
    }

    /// <summary>Deletes a file.</summary>
    [Description("Delete a file from the sandbox.")]
    public DeleteResult Delete([Description("File path to delete.")] string path)
    {
        string full = this.ResolveInRoot(path);
        string rel = this.RelativePosix(full);
        this.CheckWriteAllowed(rel);
        EnsureFile(full);
        if ((File.GetAttributes(full) & FileAttributes.ReparsePoint) != 0) { throw new FileSystemSecurityException("Refusing to delete symlink."); }
        File.Delete(full);
        return new DeleteResult(rel);
    }

    /// <summary>Moves a file.</summary>
    [Description("Move a file within the sandbox.")]
    public MoveResult Move([Description("Source path.")] string source, [Description("Destination path.")] string destination) => this.MoveImpl(source, destination);

    /// <summary>Renames a file within its current directory.</summary>
    [Description("Rename a file within its directory.")]
    public MoveResult Rename([Description("Source path.")] string path, [Description("New file name.")] string newName)
    {
        if (string.IsNullOrWhiteSpace(newName) || newName.IndexOfAny([Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar]) >= 0 || newName.Contains("..", StringComparison.Ordinal))
        {
            throw new FileSystemSecurityException("Invalid new name.");
        }
        string sourceFull = this.ResolveInRoot(path);
        string? dir = Path.GetDirectoryName(sourceFull) ?? this.Root;
        return this.MoveImpl(path, Path.Combine(this.RelativePosix(dir), newName));
    }

    internal static string GlobToRegex(string pattern) => GlobToRegexInternal(pattern);

    internal static bool TryParseRipgrepLine(string line, out GrepResult.GrepHit hit)
    {
        Match match = Regex.Match(line, @":(\d+):(.*)$", RegexOptions.None, TimeSpan.FromSeconds(1));
        if (!match.Success || !int.TryParse(match.Groups[1].Value, out int lineNumber))
        {
            hit = new GrepResult.GrepHit(string.Empty, 0, string.Empty);
            return false;
        }
        hit = new GrepResult.GrepHit(line.Substring(0, match.Index), lineNumber, match.Groups[2].Value);
        return true;
    }

    private MoveResult MoveImpl(string source, string destination)
    {
        string sourceFull = this.ResolveInRoot(source);
        string destFull = this.ResolveInRoot(destination, allowMissingLeaf: true);
        string sourceRel = this.RelativePosix(sourceFull);
        string destRel = this.RelativePosix(destFull);
        this.CheckReadAllowed(sourceRel); this.CheckWriteAllowed(sourceRel); this.CheckWriteAllowed(destRel);
        EnsureFile(sourceFull);
        if (File.Exists(destFull) || Directory.Exists(destFull)) { throw new IOException($"Destination already exists: {destRel}"); }
        Directory.CreateDirectory(Path.GetDirectoryName(destFull)!);
        File.Move(sourceFull, destFull);
        return new MoveResult(sourceRel, destRel);
    }

    private string ResolveInRoot(string path, bool allowMissingLeaf = false)
    {
        if (string.IsNullOrWhiteSpace(path)) { throw new FileSystemSecurityException("Path must not be empty."); }
        string normalizedInput = path.Replace('\\', '/');
        if (normalizedInput.Split('/').Any(s => s == "..")) { throw new FileSystemSecurityException("Path traversal is not allowed."); }
        string combined = Path.IsPathRooted(path) ? path : Path.Combine(this.Root, path);
        string resolved = Path.GetFullPath(combined);
        string containmentPath = allowMissingLeaf ? (Path.GetDirectoryName(resolved) ?? resolved) : resolved;
        if (!FileSystemPathSecurity.IsPathWithinDirectory(containmentPath, this.Root)) { throw new FileSystemSecurityException("Path escapes filesystem root."); }
        if (FileSystemPathSecurity.HasSymlinkInPath(containmentPath, this.Root)) { throw new FileSystemSecurityException("Symlinks are not allowed in paths."); }
        string rel = this.RelativePosix(resolved);
        this.CheckDenylist(rel);
        return resolved;
    }

    private string RelativePosix(string fullPath) => RelativePosix(this.Root, fullPath);

    private static string RelativePosix(string basePath, string fullPath)
    {
        string rel = GetRelativePath(basePath, fullPath);
        return rel == "." ? string.Empty : rel.Replace('\\', '/');
    }

    private void CheckDenylist(string rel)
    {
        if (this._policy.Denylist.Any(p => MatchGlob(rel, p))) { throw new FileSystemSecurityException($"Path is denied by policy: {rel}"); }
    }

    private void CheckReadAllowed(string rel)
    {
        this.CheckDenylist(rel);
        IReadOnlyList<string>? readPaths = this._policy.ReadPaths;
        if (readPaths?.Any(p => MatchGlob(rel, p)) == false) { throw new FileSystemSecurityException($"Read not allowed: {rel}"); }
    }

    private void CheckWriteAllowed(string rel)
    {
        this.CheckDenylist(rel);
        IReadOnlyList<string>? writePaths = this._policy.WritePaths;
        if (writePaths?.Any(p => MatchGlob(rel, p)) == false) { throw new FileSystemSecurityException($"Write not allowed: {rel}"); }
    }

    private string ReadText(string fullPath)
    {
        var info = new FileInfo(fullPath);
        this.EnsureWithinMaxBytes(info.Length);
        byte[] bytes = File.ReadAllBytes(fullPath);
        if (bytes.Take(Math.Min(bytes.Length, 4096)).Any(b => b == 0)) { throw new InvalidDataException("Binary files are not supported."); }
        try { return s_strictUtf8.GetString(bytes); }
        catch (DecoderFallbackException ex) { throw new InvalidDataException("File is not valid UTF-8.", ex); }
    }

    private void EnsureWithinMaxBytes(long length)
    {
        if (length > this._policy.MaxFileBytes) { throw new InvalidDataException($"File exceeds max_file_bytes ({this._policy.MaxFileBytes})."); }
    }

    private GitignoreMatcher? GetGitignore() => this._policy.RespectGitignore ? this._gitignore ??= GitignoreMatcher.Load(this.Root) : null;

    private GrepResult GrepDotNet(string pattern, bool ignoreCase, string? include)
    {
        var regex = new Regex(pattern, ignoreCase ? RegexOptions.IgnoreCase : RegexOptions.None, TimeSpan.FromSeconds(5));
        var hits = new List<GrepResult.GrepHit>();
        foreach (string file in SafeWalkFiles(this.Root, this.Root, this._policy.Denylist, this.GetGitignore()))
        {
            string rel = this.RelativePosix(file);
            if (include is not null && !MatchGlob(rel, include)) { continue; }
            this.CheckReadAllowed(rel);
            string text;
            try { text = this.ReadText(file); } catch (InvalidDataException) { continue; }
            string[] lines = SplitLines(text);
            for (int i = 0; i < lines.Length; i++)
            {
                if (regex.IsMatch(lines[i]))
                {
                    hits.Add(new GrepResult.GrepHit(rel, i + 1, lines[i]));
                    if (hits.Count >= this._policy.MaxResults) { return new GrepResult(hits, true, "python"); }
                }
            }
        }
        return new GrepResult(hits, false, "python");
    }

    private GrepResult GrepRipgrep(string pattern, bool ignoreCase, string? include)
    {
        var args = new List<string> { "--no-heading", "--line-number", "--with-filename", "--color", "never" };
        if (ignoreCase) { args.Add("--ignore-case"); }
        if (include is not null) { args.AddRange(["--glob", include]); }
        args.Add(pattern); args.Add(this.Root);
        var psi = new ProcessStartInfo { FileName = this._rgPath!, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true, WorkingDirectory = this.Root, Arguments = string.Join(" ", args.Select(QuoteArg)) };
        using var process = Process.Start(psi) ?? throw new InvalidOperationException("Failed to start rg.");
        if (!process.WaitForExit(10_000)) { try { process.Kill(); } catch (InvalidOperationException) { } throw new InvalidOperationException("rg timed out."); }
        if (process.ExitCode > 1) { throw new InvalidOperationException("rg failed."); }
        var hits = new List<GrepResult.GrepHit>();
        foreach (string line in process.StandardOutput.ReadToEnd().Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries))
        {
            if (!TryParseRipgrepLine(line, out GrepResult.GrepHit parsed)) { continue; }
            string full = Path.IsPathRooted(parsed.Path) ? parsed.Path : Path.Combine(this.Root, parsed.Path);
            string rel = this.RelativePosix(Path.GetFullPath(full));
            if (this.GetGitignore()?.IsIgnored(rel, false) == true) { continue; }
            this.CheckReadAllowed(rel);
            hits.Add(parsed with { Path = rel });
            if (hits.Count >= this._policy.MaxResults) { return new GrepResult(hits, true, "ripgrep"); }
        }
        return new GrepResult(hits, false, "ripgrep");
    }

    private static string QuoteArg(string arg) => '"' + arg.Replace("\\", "\\\\").Replace("\"", "\\\"") + '"';

    private static void EnsureFile(string fullPath)
    {
        if (!File.Exists(fullPath)) { throw new FileNotFoundException("File not found.", fullPath); }
        if (Directory.Exists(fullPath)) { throw new IOException("Expected a file."); }
    }

    private static string[] SplitLines(string text) => text.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');
    internal static string GetRelativePath(string basePath, string fullPath)
    {
        string baseFull = Path.GetFullPath(basePath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        string pathFull = Path.GetFullPath(fullPath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        if (string.Equals(baseFull, pathFull, StringComparison.OrdinalIgnoreCase))
        {
            return ".";
        }

        baseFull += Path.DirectorySeparatorChar;
        var baseUri = new Uri(baseFull);
        var pathUri = new Uri(pathFull);
        string relative = Uri.UnescapeDataString(baseUri.MakeRelativeUri(pathUri).ToString()).Replace('/', Path.DirectorySeparatorChar);
        return string.IsNullOrEmpty(relative) ? "." : relative;
    }

    private static int CountOccurrences(string text, string oldStr)
    {
        int count = 0, index = 0;
        while ((index = text.IndexOf(oldStr, index, StringComparison.Ordinal)) >= 0) { count++; index += oldStr.Length; }
        return count;
    }

    private static string ReplaceExact(string text, string oldStr, string newStr, int count)
    {
        var builder = new StringBuilder(text.Length);
        int index = 0;
        for (int i = 0; i < count; i++)
        {
            int next = text.IndexOf(oldStr, index, StringComparison.Ordinal);
            builder.Append(text, index, next - index).Append(newStr);
            index = next + oldStr.Length;
        }
        builder.Append(text, index, text.Length - index);
        return builder.ToString();
    }

    private static void AtomicWriteBytes(string path, byte[] data)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string temp = Path.Combine(Path.GetDirectoryName(path)!, ".fstool-" + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            using (var fs = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                fs.Write(data, 0, data.Length);
                fs.Flush(flushToDisk: true);
            }
            if (File.Exists(path)) { File.Replace(temp, path, null); } else { File.Move(temp, path); }
        }
        finally
        {
            if (File.Exists(temp)) { try { File.Delete(temp); } catch (IOException) { } }
        }
    }

    private static IEnumerable<string> SafeWalkFiles(string basePath, string root, IReadOnlyList<string> denylist, GitignoreMatcher? gitignore)
    {
        var stack = new Stack<string>(); stack.Push(basePath);
        while (stack.Count > 0)
        {
            string current = stack.Pop();
            IEnumerable<FileSystemInfo> entries;
            try { entries = new DirectoryInfo(current).EnumerateFileSystemInfos().ToList(); } catch (IOException) { continue; } catch (UnauthorizedAccessException) { continue; }
            foreach (FileSystemInfo entry in entries.OrderBy(e => e.FullName, StringComparer.Ordinal))
            {
                if ((entry.Attributes & FileAttributes.ReparsePoint) != 0) { continue; }
                string rel = RelativePosix(root, entry.FullName);
                bool isDir = (entry.Attributes & FileAttributes.Directory) != 0;
                if (denylist.Any(p => MatchGlob(rel, p)) || gitignore?.IsIgnored(rel, isDir) == true) { continue; }
                if (isDir) { stack.Push(entry.FullName); } else { yield return entry.FullName; }
            }
        }
    }

    private static IEnumerable<(string Path, bool IsDirectory)> WalkWithDepth(string basePath, string root, IReadOnlyList<string> denylist, int maxDepth, GitignoreMatcher? gitignore)
    {
        var stack = new Stack<(string Path, int Depth)>(); stack.Push((basePath, 0));
        while (stack.Count > 0)
        {
            (string current, int depth) = stack.Pop();
            if (depth >= maxDepth) { continue; }
            IEnumerable<FileSystemInfo> entries;
            try { entries = new DirectoryInfo(current).EnumerateFileSystemInfos().ToList(); } catch (IOException) { continue; } catch (UnauthorizedAccessException) { continue; }
            foreach (FileSystemInfo entry in entries.OrderBy(e => e.FullName, StringComparer.Ordinal))
            {
                if ((entry.Attributes & FileAttributes.ReparsePoint) != 0) { continue; }
                bool isDir = (entry.Attributes & FileAttributes.Directory) != 0;
                string rel = RelativePosix(root, entry.FullName);
                if (denylist.Any(p => MatchGlob(rel, p)) || gitignore?.IsIgnored(rel, isDir) == true) { continue; }
                yield return (entry.FullName, isDir);
                if (isDir) { stack.Push((entry.FullName, depth + 1)); }
            }
        }
    }

    internal static bool MatchGlob(string relPosix, string pattern) => Regex.IsMatch(relPosix.Replace('\\', '/'), GlobToRegexInternal(pattern.Replace('\\', '/')), RegexOptions.None, TimeSpan.FromSeconds(2));

    private static string GlobToRegexInternal(string pattern)
    {
        string[] segments = pattern.Split('/');
        var parts = new List<string>();
        for (int i = 0; i < segments.Length; i++)
        {
            string seg = segments[i]; bool last = i == segments.Length - 1;
            if (seg == "**")
            {
                if (segments.Length == 1) { parts.Add(".*"); }
                else if (i == 0) { parts.Add("(?:.*/)?"); }
                else if (last) { parts.Add("(?:/.*)?"); }
                else { parts.Add("(?:/.*/|/)"); }
            }
            else
            {
                if (i > 0 && parts.Count > 0 && !parts[^1].EndsWith("/)?", StringComparison.Ordinal) && !parts[^1].EndsWith("|/)", StringComparison.Ordinal)) { parts.Add("/"); }
                parts.Add(FnmatchToRegex(seg));
            }
        }
        return "^" + string.Concat(parts) + "$";
    }

    private static string FnmatchToRegex(string pattern)
    {
        var sb = new StringBuilder();
        for (int i = 0; i < pattern.Length; i++)
        {
            char ch = pattern[i];
            if (ch == '*') { sb.Append("[^/]*"); }
            else if (ch == '?') { sb.Append("[^/]"); }
            else if (ch == '[')
            {
                int j = pattern.IndexOf(']', i + 1);
                if (j > i) { sb.Append(pattern.Substring(i, j - i + 1)); i = j; } else { sb.Append("\\["); }
            }
            else { sb.Append(Regex.Escape(ch.ToString())); }
        }
        return sb.ToString();
    }

    private static string? FindOnPath(string name)
    {
        string? path = Environment.GetEnvironmentVariable("PATH");
        if (path is null) { return null; }
        foreach (string dir in path.Split(Path.PathSeparator))
        {
            try { string candidate = Path.Combine(dir, name); if (File.Exists(candidate)) { return candidate; } } catch (ArgumentException) { }
        }
        return null;
    }

    private static readonly UTF8Encoding s_strictUtf8 = new(false, true);
}
