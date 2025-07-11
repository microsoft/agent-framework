// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>
/// Provides helper methods for parsing key-value string representations.
/// </summary>
internal static class KeyValueParser
{
    /// <summary>
    /// Parses a string in the format "key/value" into a tuple containing the key and value.
    /// </summary>
    public static bool TryParse(string input, [NotNullWhen(true)] out string? key, [NotNullWhen(true)] out string? value)
    {
        if (!string.IsNullOrEmpty(input))
        {
            int separatorIndex = input.IndexOf('/');
            if (separatorIndex >= 0)
            {
                key = input.Substring(0, separatorIndex);
                value = input.Substring(separatorIndex + 1);
                return true;
            }
        }

        key = value = null;
        return false;
    }
}
