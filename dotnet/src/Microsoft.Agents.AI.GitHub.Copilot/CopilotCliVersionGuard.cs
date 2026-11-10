// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Globalization;
using System.Text.RegularExpressions;

namespace Microsoft.Agents.AI.GitHub.Copilot;

/// <summary>
/// Checks that the GitHub Copilot CLI in use meets the minimum supported version.
/// </summary>
internal static partial class CopilotCliVersionGuard
{
    /// <summary>The minimum supported GitHub Copilot CLI version.</summary>
    internal static readonly Version MinimumVersion = new(1, 0, 85);

    // Only the leading major.minor.patch is compared; any suffix is ignored,
    // so prerelease builds such as "1.0.85-3" count as 1.0.85.
    [GeneratedRegex(@"^\s*v?(\d+)\.(\d+)\.(\d+)", RegexOptions.CultureInvariant)]
    private static partial Regex VersionPrefixRegex();

    /// <summary>
    /// Reads the leading <c>major.minor.patch</c> from a version string.
    /// </summary>
    /// <param name="version">The version string reported by the CLI.</param>
    /// <returns>The parsed version, or <see langword="null"/> if it could not be read.</returns>
    internal static Version? Parse(string? version)
    {
        if (version is null)
        {
            return null;
        }

        Match match = VersionPrefixRegex().Match(version);
        if (!match.Success
            || !int.TryParse(match.Groups[1].Value, NumberStyles.None, CultureInfo.InvariantCulture, out int major)
            || !int.TryParse(match.Groups[2].Value, NumberStyles.None, CultureInfo.InvariantCulture, out int minor)
            || !int.TryParse(match.Groups[3].Value, NumberStyles.None, CultureInfo.InvariantCulture, out int patch))
        {
            return null;
        }

        return new Version(major, minor, patch);
    }

    /// <summary>
    /// Throws if the given CLI version is older than <see cref="MinimumVersion"/> or could not be read.
    /// </summary>
    /// <param name="version">The version string reported by the CLI.</param>
    /// <exception cref="InvalidOperationException">The version is unsupported or could not be read.</exception>
    internal static void EnsureSupported(string? version)
    {
        Version? parsed = Parse(version);
        if (parsed is null || parsed < MinimumVersion)
        {
            throw new InvalidOperationException(
                $"GitHub Copilot CLI version {MinimumVersion} or higher is required, but version '{version}' was detected.");
        }
    }

    /// <summary>
    /// Creates the error used when the CLI version could not be determined.
    /// </summary>
    /// <param name="innerException">The error raised while reading the version.</param>
    /// <returns>The exception to throw.</returns>
    internal static InvalidOperationException CreateUndeterminedVersionException(Exception innerException) =>
        new($"GitHub Copilot CLI version {MinimumVersion} or higher is required, but the version could not be determined.", innerException);
}
