// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.Diagnostics.CodeAnalysis;
using System.Text;
using System.Threading;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides process-wide tracking for Agent Framework feature usage.
/// </summary>
/// <remarks>
/// This type supports framework integrations and is not intended for direct use by applications.
/// Feature usage is accumulated for the lifetime of the process and does not represent invocation counts.
/// </remarks>
[EditorBrowsable(EditorBrowsableState.Never)]
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public static class FeatureUsage
{
    private const string FeatureMaskDisabledEnvironmentVariable = "AGENT_FRAMEWORK_FEATURE_MASK_DISABLED";
    private const int RegistryVersion = 1;

    private static long s_low;
    private static long s_high;
    private static bool s_isDisabled = ReadDisabledState();
    private static TokenCache? s_cachedToken;

    /// <summary>
    /// Marks a registered Agent Framework feature as used in the current process.
    /// </summary>
    /// <param name="index">The zero-based feature index in the range 0 through 127.</param>
    /// <exception cref="ArgumentOutOfRangeException">
    /// <paramref name="index"/> is outside the range 0 through 127 and feature-usage tracking is enabled.
    /// </exception>
    /// <remarks>
    /// Marking is idempotent. A feature bit remains set for the lifetime of the process.
    /// When <c>AGENT_FRAMEWORK_FEATURE_MASK_DISABLED</c> is set to <c>true</c> or <c>1</c>,
    /// marking is disabled and this method is a no-op.
    /// </remarks>
    public static void MarkUsed(int index)
    {
        if (Volatile.Read(ref s_isDisabled))
        {
            return;
        }

        if ((uint)index >= 128)
        {
            throw new ArgumentOutOfRangeException(nameof(index), index, "Feature index must be in the range 0 through 127.");
        }

        long bit = 1L << (index & 63);
        if (index < 64)
        {
            AtomicOr(ref s_low, bit);
        }
        else
        {
            AtomicOr(ref s_high, bit);
        }
    }

    /// <summary>
    /// Applies the current Agent Framework feature-usage token to a User-Agent value.
    /// </summary>
    /// <param name="userAgent">The existing User-Agent value.</param>
    /// <param name="includeFeatureToken">
    /// <see langword="true"/> to append or refresh the current token; <see langword="false"/> to remove any existing
    /// Agent Framework feature token.
    /// </param>
    /// <returns>
    /// The supplied User-Agent with at most one current <c>(feat=vN.hex)</c> comment, or with the feature comment
    /// removed when the token is disabled, empty, or excluded.
    /// </returns>
    /// <remarks>
    /// This infrastructure method does not approve a destination and does not sanitize the supplied User-Agent.
    /// Callers must independently verify that the actual request destination is approved before including the token.
    /// </remarks>
    public static string ApplyToUserAgent(string userAgent, bool includeFeatureToken = true)
    {
        if (userAgent is null)
        {
            throw new ArgumentNullException(nameof(userAgent));
        }

        string baseUserAgent = RemoveFeatureComments(userAgent);
        string? token = includeFeatureToken ? GetToken() : null;
        if (token is null)
        {
            return baseUserAgent;
        }

        return baseUserAgent.Length == 0
            ? $"(feat={token})"
            : $"{baseUserAgent} (feat={token})";
    }

    internal static string? GetToken()
    {
        if (Volatile.Read(ref s_isDisabled))
        {
            return null;
        }

        long low = Volatile.Read(ref s_low);
        long high = Volatile.Read(ref s_high);
        if (low == 0 && high == 0)
        {
            return null;
        }

        TokenCache? cached = Volatile.Read(ref s_cachedToken);
        if (cached is not null && low == cached.Low && high == cached.High)
        {
            return cached.Token;
        }

        string token = high == 0
            ? $"v{RegistryVersion}.{(ulong)low:x}"
            : $"v{RegistryVersion}.{(ulong)high:x}{(ulong)low:x16}";

        Volatile.Write(ref s_cachedToken, new TokenCache(low, high, token));
        return token;
    }

    /// <summary>
    /// Resets the process-global feature-usage state to isolate tests.
    /// </summary>
    /// <remarks>
    /// This test-only hook must not be used by production paths; production feature state is monotonic and never resets.
    /// </remarks>
    internal static void ResetStateForTests()
    {
        _ = Interlocked.Exchange(ref s_low, 0);
        _ = Interlocked.Exchange(ref s_high, 0);
        Volatile.Write(ref s_cachedToken, null);
        Volatile.Write(ref s_isDisabled, ReadDisabledState());
    }

    /// <summary>
    /// Reloads the cached mask-disabled environment setting without resetting the feature mask.
    /// </summary>
    /// <remarks>
    /// This test-only hook verifies startup-cached configuration behavior without clearing observed feature state.
    /// Production paths read the setting once when this type initializes.
    /// </remarks>
    internal static void ReloadDisabledStateForTests()
        => Volatile.Write(ref s_isDisabled, ReadDisabledState());

    private static void AtomicOr(ref long location, long value)
    {
        if ((Volatile.Read(ref location) & value) != 0)
        {
            return;
        }

#if NETSTANDARD2_0 || NETFRAMEWORK
        long current;
        long updated;
        do
        {
            current = Volatile.Read(ref location);
            updated = current | value;
            if (current == updated)
            {
                return;
            }
        }
        while (Interlocked.CompareExchange(ref location, updated, current) != current);
#else
        _ = Interlocked.Or(ref location, value);
#endif
    }

    private static bool ReadDisabledState()
    {
        string? value = Environment.GetEnvironmentVariable(FeatureMaskDisabledEnvironmentVariable);
        return string.Equals(value, "true", StringComparison.OrdinalIgnoreCase)
            || string.Equals(value, "1", StringComparison.OrdinalIgnoreCase);
    }

    private static string RemoveFeatureComments(string userAgent)
    {
        if (!TryFindFeatureComment(userAgent, searchFrom: 0, out int commentStart, out int commentEnd))
        {
            return userAgent;
        }

        var result = new StringBuilder(userAgent.Length);
        int copyFrom = 0;
        do
        {
            int removeFrom = commentStart;
            int removeThrough = commentEnd;

            if (removeFrom > copyFrom && char.IsWhiteSpace(userAgent[removeFrom - 1]))
            {
                removeFrom--;
            }
            else if (removeFrom == copyFrom &&
                removeThrough < userAgent.Length &&
                char.IsWhiteSpace(userAgent[removeThrough]))
            {
                removeThrough++;
            }

            result.Append(userAgent, copyFrom, removeFrom - copyFrom);
            copyFrom = removeThrough;
        }
        while (TryFindFeatureComment(userAgent, commentEnd, out commentStart, out commentEnd));

        result.Append(userAgent, copyFrom, userAgent.Length - copyFrom);
        return result.ToString();
    }

    private static bool TryFindFeatureComment(string userAgent, int searchFrom, out int start, out int end)
    {
        const string Prefix = "(feat=v";

        while ((start = userAgent.IndexOf(Prefix, searchFrom, StringComparison.Ordinal)) >= 0)
        {
            if (start > 0 && !char.IsWhiteSpace(userAgent[start - 1]))
            {
                searchFrom = start + Prefix.Length;
                continue;
            }

            int cursor = start + Prefix.Length;
            int versionStart = cursor;
            while (cursor < userAgent.Length && userAgent[cursor] is >= '0' and <= '9')
            {
                cursor++;
            }

            if (cursor == versionStart || cursor >= userAgent.Length || userAgent[cursor] != '.')
            {
                searchFrom = start + Prefix.Length;
                continue;
            }

            cursor++;
            int maskStart = cursor;
            while (cursor < userAgent.Length && IsHexDigit(userAgent[cursor]))
            {
                cursor++;
            }

            if (cursor == maskStart || cursor >= userAgent.Length || userAgent[cursor] != ')')
            {
                searchFrom = start + Prefix.Length;
                continue;
            }

            end = cursor + 1;
            if (end == userAgent.Length || char.IsWhiteSpace(userAgent[end]))
            {
                return true;
            }

            searchFrom = start + Prefix.Length;
        }

        start = -1;
        end = -1;
        return false;
    }

    private static bool IsHexDigit(char value)
        => value is >= '0' and <= '9'
            or >= 'a' and <= 'f'
            or >= 'A' and <= 'F';

    private sealed class TokenCache(long low, long high, string token)
    {
        public long Low { get; } = low;

        public long High { get; } = high;

        public string Token { get; } = token;
    }
}
