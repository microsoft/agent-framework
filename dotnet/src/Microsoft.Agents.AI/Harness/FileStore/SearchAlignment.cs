// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI;

/// <summary>
/// Checks that a store's reported line numbers address the same lines the line editor will edit.
/// </summary>
/// <remarks>
/// <para>
/// <c>grep</c> takes its <see cref="FileSearchMatch.LineNumber"/> values from the store, while
/// <c>read_lines</c> and <c>replace_lines</c> re-count them from <see cref="AgentFileStore.ReadAsync"/>.
/// A store that overrides <see cref="AgentFileStore.SearchAsync"/> and numbers lines differently makes
/// those two disagree, and an edit then lands on the wrong line — in range, reporting success.
/// </para>
/// <para>
/// The check is skipped for a store that uses the base <see cref="AgentFileStore.SearchAsync"/>
/// (aligned by construction) or declares <see cref="AgentFileStore.ReportsAlignedLineNumbers"/>.
/// Otherwise every reported number is re-checked by running the pattern against that line of
/// <see cref="AgentFileStore.SplitLines"/>, which is what <c>replace_lines</c> indexes into. Matching
/// by pattern rather than by string equality is deliberate: a custom store is not required to report
/// the line verbatim with its terminator, so comparing text would reject correct stores.
/// </para>
/// <para>
/// This is detection, not proof — a pattern matching every line (<c>.</c>) passes even if the
/// numbering is skewed — and it is deliberately whole-call: one skewed file means the store's
/// coordinates cannot be trusted anywhere.
/// </para>
/// </remarks>
internal static class SearchAlignment
{
    internal const string MisalignedMessage =
        "This store's line numbers do not line up with the numbering used by read_lines and " +
        "replace_lines, so editing by the reported numbers would change the wrong lines (or a file " +
        "changed while the search ran). Use read or read_lines to locate the content before editing.";

    /// <summary>
    /// Throws when <paramref name="results"/> cannot be trusted to address the editor's lines.
    /// </summary>
    internal static async Task ThrowIfMisalignedAsync(
        AgentFileStore store,
        string directory,
        IReadOnlyList<FileSearchResult> results,
        string regexPattern,
        CancellationToken cancellationToken,
        string? misalignedMessage = null, // The memory provider passes its own; it registers no read_lines.
        TimeSpan? matchTimeout = null) // Overridable so a test can reach the timeout path.
    {
        if (results.Count == 0 || IsTrusted(store, results))
        {
            return;
        }

        string failure = misalignedMessage ?? MisalignedMessage;

        // A store that supplies its own SearchAsync may have matched with a different engine or
        // dialect. If the pattern will not compile here there is nothing to check against, and
        // failing to verify is not the same as finding a mismatch -- the store already accepted it.
        Regex regex;
        try
        {
            regex = new Regex(regexPattern, RegexOptions.IgnoreCase, matchTimeout ?? TimeSpan.FromSeconds(5));
        }
        catch (ArgumentException)
        {
            return;
        }

        foreach (FileSearchResult result in results)
        {
            string path = string.IsNullOrEmpty(directory)
                ? result.FileName
                : $"{directory.TrimEnd('/')}/{result.FileName}";

            string? content = await store.ReadAsync(path, cancellationToken).ConfigureAwait(false);
            if (content is null)
            {
                // Deleted between the search and this check. The base SearchAsync treats the same
                // race as benign, so it must not be reported here as a store-correctness fault.
                continue;
            }

            IReadOnlyList<string> lines = AgentFileStore.SplitLines(content);
            foreach (FileSearchMatch match in result.MatchingLines)
            {
                // Both bounds: 0 or negative would index out of range below instead of reporting misalignment.
                if (match.LineNumber < 1 || match.LineNumber > lines.Count)
                {
                    throw new InvalidOperationException(failure);
                }

                string line = lines[match.LineNumber - 1];
                bool matched;
                try
                {
                    matched = regex.Match(line, 0, FileEditor.LineContentLength(line)).Success;
                }
                catch (RegexMatchTimeoutException)
                {
                    // Skip this match only; returning would leave every later result unchecked but reported.
                    continue;
                }

                if (!matched)
                {
                    throw new InvalidOperationException(failure);
                }
            }
        }
    }

    /// <summary>
    /// Returns whether the store's line numbers are known to be aligned without checking.
    /// </summary>
    private static bool IsTrusted(AgentFileStore store, IReadOnlyList<FileSearchResult> results)
    {
        // Trusted when the store declares alignment, or when these particular results carry the
        // base implementation's tag -- which is per call, so an earlier delegation to
        // base.SearchAsync cannot vouch for results the store numbered itself.
        return store.ReportsAlignedLineNumbers || results is BaseSearchResults;
    }
}
