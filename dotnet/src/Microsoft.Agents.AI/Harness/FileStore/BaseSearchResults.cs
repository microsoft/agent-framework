// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;

namespace Microsoft.Agents.AI;

/// <summary>
/// Marks a result set as having been numbered by the base <see cref="AgentFileStore.SearchAsync"/>.
/// </summary>
/// <remarks>
/// <para>
/// The alignment check needs to know whether the line numbers it is about to hand to the model came
/// from the base implementation (aligned by construction) or from a store's own
/// <see cref="AgentFileStore.SearchAsync"/>. Reflecting over the store's type is not trim-safe, and a
/// flag on the store would be per instance rather than per call — a store that defers to
/// <c>base.SearchAsync</c> only sometimes would buy permanent trust for the results it numbers itself,
/// which is exactly the failure the check exists to catch.
/// </para>
/// <para>
/// Tagging the returned list keeps the signal with the data, but the tag alone only says who built
/// the list, not that its contents are still theirs: the list and every <see cref="FileSearchResult"/>
/// in it are mutable, so an override could renumber them in place and keep the tag. The numbers are
/// therefore snapshotted at construction and re-checked by <see cref="IsUnmodified"/>, so any edit --
/// or a rebuilt list, which loses the tag outright -- falls back to verification rather than trust.
/// </para>
/// </remarks>
internal sealed class BaseSearchResults : List<FileSearchResult>
{
    private readonly (string FileName, int[] LineNumbers)[] _numbered;

    internal BaseSearchResults(IReadOnlyList<FileSearchResult> results)
        : base(results)
    {
        this._numbered = new (string FileName, int[] LineNumbers)[results.Count];
        for (int i = 0; i < results.Count; i++)
        {
            FileSearchResult result = results[i];
            int[] lineNumbers = new int[result.MatchingLines.Count];
            for (int j = 0; j < lineNumbers.Length; j++)
            {
                lineNumbers[j] = result.MatchingLines[j].LineNumber;
            }

            this._numbered[i] = (result.FileName, lineNumbers);
        }
    }

    /// <summary>
    /// Returns whether the file names and line numbers still match what the base implementation produced.
    /// </summary>
    /// <remarks>
    /// <see cref="FileSearchMatch.Line"/> is deliberately not covered: a store may report the text
    /// differently, which is why the alignment check matches by pattern rather than by string.
    /// </remarks>
    internal bool IsUnmodified()
    {
        if (this.Count != this._numbered.Length)
        {
            return false;
        }

        for (int i = 0; i < this.Count; i++)
        {
            FileSearchResult result = this[i];
            (string fileName, int[] lineNumbers) = this._numbered[i];
            if (result is null ||
                !string.Equals(result.FileName, fileName, StringComparison.Ordinal) ||
                result.MatchingLines is null ||
                result.MatchingLines.Count != lineNumbers.Length)
            {
                return false;
            }

            for (int j = 0; j < lineNumbers.Length; j++)
            {
                if (result.MatchingLines[j].LineNumber != lineNumbers[j])
                {
                    return false;
                }
            }
        }

        return true;
    }
}
