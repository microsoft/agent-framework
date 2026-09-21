// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.FileSystemGlobbing;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

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
    /// <remarks>
    /// <para>
    /// Implementers overriding this method must report <see cref="FileSearchMatch.LineNumber"/> as a
    /// 1-based coordinate into <see cref="SplitLines"/> of the same content <see cref="ReadAsync"/>
    /// returns, and should report <see cref="FileSearchMatch.Line"/> verbatim, terminator included.
    /// <see cref="ScanContent"/> produces both correctly and is the recommended way to build results.
    /// </para>
    /// <para>
    /// Numbering against anything else — a different split rule, or content this store does not serve
    /// through <see cref="ReadAsync"/> — is a bug with a silent failure mode: the search looks correct,
    /// and the damage appears later when a line edit applies to a line the caller never saw. Cover it
    /// with a test that greps and then edits by the reported number.
    /// </para>
    /// </remarks>
    public virtual async Task<IReadOnlyList<FileSearchResult>> SearchAsync(string directory, string regexPattern, string? globPattern = null, bool recursive = false, CancellationToken cancellationToken = default)
    {
        // Compile with a match timeout to guard against catastrophic backtracking (ReDoS).
        var regex = new Regex(regexPattern, RegexOptions.IgnoreCase, TimeSpan.FromSeconds(5));
        IReadOnlyList<string> names = await this.FindMatchingFilesAsync(directory, regexPattern, globPattern, recursive, cancellationToken).ConfigureAwait(false);
        Matcher? matcher = globPattern is not null ? StorePaths.CreateGlobMatcher(globPattern) : null;
        var results = new List<FileSearchResult>();

        foreach (string name in names)
        {
            cancellationToken.ThrowIfCancellationRequested();

            // Re-apply the caller's scope: FindMatchingFilesAsync is explicitly allowed to
            // over-return, and must not be able to widen what the caller asked for.
            if (!StorePaths.MatchesGlob(name, matcher) ||
                (!recursive && name.IndexOf("/", StringComparison.Ordinal) >= 0))
            {
                continue;
            }

            string path = string.IsNullOrEmpty(directory) ? name : $"{directory.TrimEnd('/')}/{name}";
            string? content = await this.ReadAsync(path, cancellationToken).ConfigureAwait(false);
            if (content is null)
            {
                continue; // Deleted between enumeration and read.
            }

            FileSearchResult? result = ScanContent(name, content, regex);
            if (result is not null)
            {
                results.Add(result);
            }
        }

        return results;
    }

    /// <summary>
    /// Gets the names of the files that <em>may</em> contain text that matches
    /// <paramref name="regexPattern"/> and where file names <em>may</em> match
    /// <paramref name="globPattern"/>.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This is the hook a store uses to narrow the search to the files worth reading. Semantics are
    /// deliberately a <b>superset</b>: returning a file that turns out not to match is harmless,
    /// because <see cref="SearchAsync"/> re-scans every candidate, while omitting one loses the match.
    /// A backend with a native search index should override this and push
    /// <paramref name="regexPattern"/> down to it, widening rather than guessing where the dialect
    /// cannot express the pattern.
    /// </para>
    /// <para>
    /// The default implementation has no index to narrow with, so it walks
    /// <see cref="ListChildrenAsync"/> and returns every file in scope, leaving
    /// <see cref="SearchAsync"/> to read and scan all of them. Override this when the backing store
    /// can answer either question more cheaply than that — a name index for
    /// <paramref name="globPattern"/>, a content or full-text index for <paramref name="regexPattern"/> —
    /// and return the candidates it finds. That is the whole purpose of the hook: the store does the
    /// narrowing it is good at, and the base keeps the scanning and the line numbering. Overriding
    /// <see cref="SearchAsync"/> instead is also supported, but then line numbering is the store's
    /// responsibility (see <see cref="SplitLines"/>), and nothing checks it at runtime.
    /// </para>
    /// </remarks>
    /// <param name="directory">The relative directory being searched. Use an empty string for the root.</param>
    /// <param name="regexPattern">
    /// The pattern <see cref="SearchAsync"/> was called with, as a hint. It is matched
    /// case-insensitively, so an index that cannot search that way must widen rather than narrow:
    /// returning only case-exact candidates drops matches the caller would have got.
    /// </param>
    /// <param name="globPattern">
    /// The optional glob, matched against each file's path relative to <paramref name="directory"/>,
    /// also case-insensitively. The same rule applies — widen when the backend cannot reproduce it.
    /// </param>
    /// <param name="recursive">When <see langword="false"/> only direct children are in scope.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>File paths relative to <paramref name="directory"/>, using forward slashes.</returns>
    protected virtual async Task<IReadOnlyList<string>> FindMatchingFilesAsync(string directory, string regexPattern, string? globPattern = null, bool recursive = false, CancellationToken cancellationToken = default)
    {
        _ = regexPattern; // No index to narrow with here; a backend with one overrides this.
        var names = new List<string>();
        var pending = new Stack<string>();
        pending.Push(string.Empty);

        while (pending.Count > 0)
        {
            // Checked here as well as passed down: a store whose ListChildrenAsync ignores the token
            // would otherwise let a cancelled walk enumerate the whole hierarchy one listing at a time.
            cancellationToken.ThrowIfCancellationRequested();

            string relativeDir = pending.Pop();
            string target = string.IsNullOrEmpty(relativeDir)
                ? directory
                : (string.IsNullOrEmpty(directory) ? relativeDir : $"{directory.TrimEnd('/')}/{relativeDir}");

            foreach (FileStoreEntry entry in await this.ListChildrenAsync(target, cancellationToken).ConfigureAwait(false))
            {
                cancellationToken.ThrowIfCancellationRequested();

                string child = string.IsNullOrEmpty(relativeDir) ? entry.Name : $"{relativeDir}/{entry.Name}";
                if (entry.Type == FileStoreEntry.Directory)
                {
                    if (recursive)
                    {
                        pending.Push(child);
                    }
                }
                else
                {
                    names.Add(child);
                }
            }
        }

        return names;
    }

    /// <summary>
    /// Splits <paramref name="content"/> into the lines this SDK's line numbers address.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This is the published definition of a line for the whole file-access surface: the
    /// <c>read_lines</c> and <c>replace_lines</c> tools, and every <see cref="FileSearchMatch.LineNumber"/>
    /// reported by <see cref="SearchAsync"/>, are coordinates in this list. Each line keeps its
    /// terminator (<c>\r\n</c>, <c>\n</c>, or a lone <c>\r</c>), and the final line has none when the
    /// content does not end with a newline.
    /// </para>
    /// <para>
    /// A store that overrides <see cref="SearchAsync"/> must number its matches by this split,
    /// otherwise grep and the line editor disagree and an edit lands on the wrong line. The rule is
    /// per-SDK: it is not required to match the Python implementation, only to be consistent within
    /// this one, because a line number never crosses runtimes.
    /// </para>
    /// </remarks>
    /// <param name="content">The full text to split.</param>
    /// <returns>The lines, each with its terminator attached.</returns>
    public static IReadOnlyList<string> SplitLines(string content) => FileEditor.SplitLinesKeepEnds(Throw.IfNull(content));

    /// <summary>
    /// Finds every line of <paramref name="content"/> matching <paramref name="regex"/>, numbered by
    /// <see cref="SplitLines"/>.
    /// </summary>
    /// <remarks>
    /// This is the numbering primitive <see cref="SearchAsync"/> uses, published so a store that
    /// supplies its own <see cref="SearchAsync"/> can produce aligned results rather than re-deriving
    /// them. Lines are reported verbatim, terminator included; the pattern is matched against the
    /// line without its terminator, so an end-anchored pattern behaves the same on CRLF content.
    /// </remarks>
    /// <param name="fileName">The name recorded on the result, relative to the searched directory.</param>
    /// <param name="content">The file's full text.</param>
    /// <param name="regex">A compiled pattern, normally from the same source string passed to <see cref="SearchAsync"/>.</param>
    /// <returns>The match metadata, or <see langword="null"/> when no line matches.</returns>
    public static FileSearchResult? ScanContent(string fileName, string content, Regex regex)
    {
        _ = Throw.IfNull(fileName);
        _ = Throw.IfNull(content);
        _ = Throw.IfNull(regex);

        IReadOnlyList<string> lines = SplitLines(content);
        var matchingLines = new List<FileSearchMatch>();
        string? firstSnippet = null;
        int lineStartOffset = 0;

        for (int i = 0; i < lines.Count; i++)
        {
            // Match over the line's text only, without copying it out of the line.
            Match match = regex.Match(lines[i], 0, FileEditor.LineContentLength(lines[i]));
            if (match.Success)
            {
                matchingLines.Add(new FileSearchMatch { LineNumber = i + 1, Line = lines[i] });

                // Build a context snippet around the first match (+/-50 chars).
                if (firstSnippet is null)
                {
                    int charIndex = lineStartOffset + match.Index;
                    int snippetStart = Math.Max(0, charIndex - 50);
                    int snippetEnd = Math.Min(content.Length, charIndex + match.Value.Length + 50);
                    firstSnippet = content.Substring(snippetStart, snippetEnd - snippetStart);
                }
            }

            // Advance past this line; its terminator is already part of its length.
            lineStartOffset += lines[i].Length;
        }

        return matchingLines.Count == 0
            ? null
            : new FileSearchResult { FileName = fileName, Snippet = firstSnippet!, MatchingLines = matchingLines };
    }

    /// <summary>
    /// Ensures a directory exists, creating it if necessary.
    /// </summary>
    /// <param name="path">The relative path of the directory to create.</param>
    /// <param name="cancellationToken">A token to cancel the operation.</param>
    /// <returns>A task representing the asynchronous operation.</returns>
    public abstract Task CreateDirectoryAsync(string path, CancellationToken cancellationToken = default);
}
