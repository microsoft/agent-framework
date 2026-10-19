// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Text.RegularExpressions;
using System.Threading;

namespace Microsoft.Agents.AI;

/// <summary>
/// Matches file content while enforcing one time budget across the entire search.
/// </summary>
/// <remarks>
/// Each individual match is limited to five seconds. When less time remains in the shared
/// ten-second search budget, the remaining time is used instead so each new line cannot reset
/// the protection against excessive regex backtracking.
/// </remarks>
internal sealed class FileSearchRegexWithTimeout
{
    private static readonly TimeSpan s_matchTimeout = TimeSpan.FromSeconds(5);
    private static readonly TimeSpan s_searchTimeout = TimeSpan.FromSeconds(10);

    private readonly string _pattern;
    private readonly Regex _regex;
    private readonly TimeSpan _searchTimeout;
    private readonly Func<TimeSpan> _getElapsedTime;

    /// <summary>
    /// Initializes a case-insensitive file-search regex and starts its shared search timer.
    /// </summary>
    /// <param name="pattern">The regular expression pattern to match.</param>
    public FileSearchRegexWithTimeout(string pattern)
    {
        this._pattern = pattern;
        this._regex = new Regex(pattern, RegexOptions.IgnoreCase, s_matchTimeout);
        this._searchTimeout = s_searchTimeout;

        Stopwatch stopwatch = Stopwatch.StartNew();
        this._getElapsedTime = () => stopwatch.Elapsed;
    }

    /// <summary>
    /// Initializes a file-search regex with a custom budget and elapsed-time source for testing.
    /// </summary>
    /// <param name="pattern">The regular expression pattern to match.</param>
    /// <param name="searchTimeout">The total time available for the search.</param>
    /// <param name="getElapsedTime">Returns the time elapsed since the search began.</param>
    internal FileSearchRegexWithTimeout(string pattern, TimeSpan searchTimeout, Func<TimeSpan> getElapsedTime)
    {
        this._pattern = pattern;
        this._regex = new Regex(pattern, RegexOptions.IgnoreCase, Min(s_matchTimeout, searchTimeout));
        this._searchTimeout = searchTimeout;
        this._getElapsedTime = getElapsedTime;
    }

    /// <summary>
    /// Matches the requested portion of a line using the remaining shared search budget.
    /// </summary>
    /// <param name="input">The line containing the text to match.</param>
    /// <param name="length">The number of characters to include in the match.</param>
    /// <param name="cancellationToken">A token to cancel the search.</param>
    /// <returns>The regex match.</returns>
    /// <exception cref="OperationCanceledException">The search was cancelled.</exception>
    /// <exception cref="RegexMatchTimeoutException">The individual match or total search exceeded its time limit.</exception>
    public Match Match(string input, int length, CancellationToken cancellationToken)
    {
        TimeSpan remaining = this.GetRemainingTime(cancellationToken);

        Regex regex = remaining < s_matchTimeout
            ? new Regex(this._pattern, RegexOptions.IgnoreCase, remaining)
            : this._regex;
        Match match = regex.Match(input, 0, length);

        cancellationToken.ThrowIfCancellationRequested();
        if (this._getElapsedTime() >= this._searchTimeout)
        {
            this.ThrowSearchTimeout();
        }

        return match;
    }

    /// <summary>
    /// Throws when the search was cancelled or its shared time budget has expired.
    /// </summary>
    /// <param name="cancellationToken">A token to cancel the search.</param>
    /// <exception cref="OperationCanceledException">The search was cancelled.</exception>
    /// <exception cref="RegexMatchTimeoutException">The total search exceeded its time limit.</exception>
    public void ThrowIfExpired(CancellationToken cancellationToken) => _ = this.GetRemainingTime(cancellationToken);

    private TimeSpan GetRemainingTime(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();

        TimeSpan remaining = this._searchTimeout - this._getElapsedTime();
        if (remaining <= TimeSpan.Zero)
        {
            this.ThrowSearchTimeout();
        }

        return remaining;
    }

    private static TimeSpan Min(TimeSpan left, TimeSpan right) => left <= right ? left : right;

    [DoesNotReturn]
    private void ThrowSearchTimeout() =>
        throw new RegexMatchTimeoutException(string.Empty, this._pattern, this._searchTimeout);
}
