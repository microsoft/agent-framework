// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Describes whether a skill provides a complete file list or allows files to be requested without one.
/// </summary>
/// <remarks>
/// The <c>resources</c> field in an MCP skill entry is either an array of file descriptions
/// (<see cref="McpSkillManifestResources"/>) or the string <c>"dynamic"</c> (<see cref="McpSkillDynamicResources"/>).
/// Neither form contains file content; files are read separately, only when needed.
/// <see cref="AgentMcpSkill"/> uses this information to restrict reads and check fetched content.
/// It also handles fetching, caching, path safety, size limits, and frontmatter validation.
/// </remarks>
internal abstract class McpSkillResources;

/// <summary>
/// The server's complete file list, with the address, expected size, and hash of each file.
/// </summary>
/// <remarks>
/// Includes <c>SKILL.md</c> and every supporting file. Reads are limited to listed files,
/// and fetched content is checked against its expected size and hash.
/// </remarks>
internal sealed class McpSkillManifestResources : McpSkillResources
{
    private readonly Dictionary<string, McpSkillResourceEntry> _entriesByUri;

    /// <summary>
    /// Initializes the file list used to restrict reads and verify fetched content.
    /// </summary>
    /// <param name="entries">Every file in the skill, including <c>SKILL.md</c>, with its expected size and hash.</param>
    public McpSkillManifestResources(IReadOnlyList<McpSkillResourceEntry> entries)
    {
        this.Entries = Throw.IfNull(entries);
        this._entriesByUri = new(entries.Count, StringComparer.Ordinal);

        // Keep the original list so the catalog can report null entries and duplicate URIs.
        foreach (McpSkillResourceEntry? entry in entries)
        {
            if (entry?.Uri is string uri)
            {
                this._entriesByUri.TryAdd(uri, entry);
            }
        }
    }

    /// <summary>
    /// Gets the server's complete file list, including <c>SKILL.md</c>.
    /// </summary>
    public IReadOnlyList<McpSkillResourceEntry> Entries { get; }

    /// <summary>
    /// Finds the listed file with the specified URI.
    /// </summary>
    /// <param name="uri">The resource URI to look up.</param>
    /// <returns>The matching entry, or <see langword="null"/> if the file is not listed.</returns>
    public McpSkillResourceEntry? FindEntry(string uri) =>
        this._entriesByUri.TryGetValue(uri, out McpSkillResourceEntry? entry) ? entry : null;
}

/// <summary>
/// Indicates that the server provides no file list.
/// </summary>
/// <remarks>
/// <c>SKILL.md</c> is addressed by the skill entry's URI. Supporting files are requested by relative path
/// within the skill's directory, for example when referenced in the instructions.
/// Content can change between reads after the cache expires, without a manifest to verify it against.
/// Reads still enforce size limits and check that <c>SKILL.md</c> metadata matches the skill entry.
/// </remarks>
internal sealed class McpSkillDynamicResources : McpSkillResources;
