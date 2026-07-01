// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;

namespace Microsoft.Agents.AI;

/// <summary>
/// Configuration options for <see cref="AgentMcpSkillsSource"/>.
/// </summary>
public sealed class AgentMcpSkillsSourceOptions
{
    /// <summary>
    /// Gets or sets the base directory that archive-type skills are extracted to and served from.
    /// </summary>
    /// <remarks>
    /// Archives are extracted beneath this directory as <c>{ArchiveSkillsDirectory}/{skill-name}/</c>.
    /// When <see langword="null"/>, the source extracts to a per-instance unique location of
    /// <c>{currentDirectory}/{guid}/{skill-name}/</c>, where the GUID is generated once per
    /// <see cref="AgentMcpSkillsSource"/> instance so that multiple sources never overwrite one
    /// another. Set this to a fixed value to get a predictable, reusable extraction location.
    /// When set, each source must use its own unique directory: the source treats the directory as
    /// exclusively its own and, on every discovery, prunes any sub-directory that the MCP server no
    /// longer advertises or whose index entry is not actionable (e.g., missing a required field).
    /// Pointing two sources at the same directory would therefore cause them to
    /// delete each other's extracted skills.
    /// </remarks>
    public string? ArchiveSkillsDirectory { get; set; }

    /// <summary>
    /// Gets or sets the allowed file extensions for resources discovered in extracted archive-type skills.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, defaults to <c>.md</c>, <c>.json</c>, <c>.yaml</c>, <c>.yml</c>,
    /// <c>.csv</c>, <c>.xml</c>, and <c>.txt</c>.
    /// </remarks>
    public IEnumerable<string>? ArchiveResourceExtensions { get; set; }

    /// <summary>
    /// Gets or sets the maximum depth to search for resource files within each extracted archive-type
    /// skill directory. A value of <c>1</c> searches only the skill root directory. A value of <c>2</c>
    /// searches the root and one level of subdirectories.
    /// </summary>
    /// <remarks>
    /// When <see langword="null"/>, the source uses the default depth of <c>2</c>.
    /// </remarks>
    public int? ArchiveResourceSearchDepth { get; set; }

    /// <summary>
    /// Gets or sets the maximum number of files that may be extracted from a single archive-type skill.
    /// </summary>
    /// <remarks>
    /// Guards against excessive-file-count denial-of-service archives. When <see langword="null"/>, the
    /// source uses a default of <c>20</c>, sized for a typical well-formed skill (a handful of files).
    /// Raise this for archive-type skills that legitimately bundle many files. An archive that exceeds
    /// the limit is skipped.
    /// </remarks>
    public int? ArchiveMaxFileCount { get; set; }

    /// <summary>
    /// Gets or sets the maximum size, in bytes, of a downloaded archive-type skill resource.
    /// </summary>
    /// <remarks>
    /// Guards against archive resources that are too large to materialize safely. When
    /// <see langword="null"/>, the source uses a default of <c>1 MB</c>, sized for a typical
    /// well-formed skill archive. Raise this for archive-type skills that legitimately require
    /// larger archive payloads. An archive that exceeds the limit is skipped.
    /// </remarks>
    public long? ArchiveMaxSizeBytes { get; set; }

    /// <summary>
    /// Gets or sets the maximum total uncompressed size, in bytes, of all files extracted from a single
    /// archive-type skill.
    /// </summary>
    /// <remarks>
    /// Guards against decompression-bomb archives. When <see langword="null"/>, the source uses a default
    /// of <c>1 MB</c>, sized for a typical well-formed skill (well under ~1 MB). Raise this for
    /// archive-type skills that legitimately bundle larger content. An archive that exceeds the limit is
    /// skipped.
    /// </remarks>
    public long? ArchiveMaxUncompressedSizeBytes { get; set; }
}
