// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;

namespace Microsoft.Agents.AI;

/// <summary>
/// The path trust boundary of a discovered file-backed skill: the host-configured discovery
/// root together with the skill directory that was found at or beneath it.
/// </summary>
/// <remarks>
/// <para>
/// The configured root is retained alongside the skill directory so that a file can be
/// revalidated immediately before use against every directory from the root down to the file,
/// rather than only the segments below the skill directory. Without the root, a skill directory
/// (or a directory between it and the root) that was swapped for a link after discovery would
/// never be inspected.
/// </para>
/// <para>
/// The configured root itself is never inspected: the host chose it explicitly, so it defines the
/// trust boundary rather than sitting inside it, and it is allowed to be a link.
/// </para>
/// </remarks>
internal sealed class AgentFileSkillPathScope
{
    private static readonly string s_directorySeparator = Path.DirectorySeparatorChar.ToString();

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentFileSkillPathScope"/> class.
    /// </summary>
    /// <param name="trustedRootFullPath">The host-configured discovery root the skill was found under.</param>
    /// <param name="skillDirectoryFullPath">The discovered skill directory, at or beneath the configured root.</param>
    /// <exception cref="ArgumentException">The skill directory does not reside at or beneath the configured root.</exception>
    public AgentFileSkillPathScope(string trustedRootFullPath, string skillDirectoryFullPath)
    {
        this.SkillDirectoryPath = Path.GetFullPath(skillDirectoryFullPath);
        this.SkillDirectoryPrefix = EnsureTrailingSeparator(this.SkillDirectoryPath);
        this.TrustedRootPrefix = EnsureTrailingSeparator(Path.GetFullPath(trustedRootFullPath));

        if (!this.SkillDirectoryPrefix.StartsWith(this.TrustedRootPrefix, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException(
                "The skill directory must reside at or beneath the configured skill discovery root.",
                nameof(skillDirectoryFullPath));
        }
    }

    /// <summary>
    /// Gets the absolute path of the skill directory.
    /// </summary>
    public string SkillDirectoryPath { get; }

    /// <summary>
    /// Gets the skill directory with a trailing separator, for path-containment checks and for
    /// computing paths relative to the skill directory.
    /// </summary>
    /// <remarks>
    /// The trailing separator stops containment checks from false-matching sibling directories.
    /// e.g. "/skills/myskill" matches "/skills/myskill-evil/", but "/skills/myskill/" does not.
    /// </remarks>
    public string SkillDirectoryPrefix { get; }

    /// <summary>
    /// Gets the configured discovery root with a trailing separator, used as the base for
    /// link and reparse point scans so that every segment beneath it is inspected.
    /// </summary>
    public string TrustedRootPrefix { get; }

    private static string EnsureTrailingSeparator(string fullPath)
    {
        string trimmedPath = fullPath.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);

        return string.Concat(trimmedPath, s_directorySeparator);
    }
}
