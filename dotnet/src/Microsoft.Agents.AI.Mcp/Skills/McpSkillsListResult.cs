// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI;

/// <summary>
/// The result returned by <c>skills/list</c>.
/// </summary>
internal sealed class McpSkillsListResult
{
    /// <summary>
    /// Gets the result type, which must be <c>complete</c>.
    /// </summary>
    public required string ResultType { get; init; }

    /// <summary>
    /// Gets the skills listed by the server.
    /// </summary>
    public required IReadOnlyList<McpSkillEntry?> Skills { get; init; }

    /// <summary>
    /// Gets the opaque cursor to pass to the next request, or <see langword="null"/> when no more pages are available.
    /// </summary>
    public string? NextCursor { get; init; }

    /// <summary>
    /// Gets the server's freshness hint for this page. Missing or nonpositive values are immediately stale.
    /// </summary>
    [JsonPropertyName("ttlMs")]
    [JsonConverter(typeof(TimeSpanMillisecondsConverter))]
    public TimeSpan? TimeToLive { get; init; }
}

/// <summary>
/// A skill entry returned by <c>skills/list</c>.
/// </summary>
internal sealed class McpSkillEntry
{
    /// <summary>
    /// Gets the resource URI of the skill's <c>SKILL.md</c>.
    /// </summary>
    public required string Uri { get; init; }

    /// <summary>
    /// Gets the skill's name and description.
    /// </summary>
    public required McpSkillFrontmatter Frontmatter { get; init; }

    /// <summary>
    /// Gets the resources listed for the skill.
    /// </summary>
    public required IReadOnlyList<McpSkillResourceEntry> Resources { get; init; }
}

/// <summary>
/// The name and description of a skill returned by <c>skills/list</c>.
/// </summary>
internal sealed class McpSkillFrontmatter
{
    /// <summary>
    /// Gets the skill's name.
    /// </summary>
    public required string Name { get; init; }

    /// <summary>
    /// Gets the skill's description.
    /// </summary>
    public required string Description { get; init; }
}

/// <summary>
/// A resource entry returned by <c>skills/list</c>.
/// </summary>
internal sealed class McpSkillResourceEntry
{
    /// <summary>
    /// Gets the file's resource URI.
    /// </summary>
    public required string Uri { get; init; }

    /// <summary>
    /// Gets the SHA-256 digest of the file's bytes as <c>sha256:</c> followed by 64 lowercase hexadecimal characters.
    /// </summary>
    public required string Digest { get; init; }

    /// <summary>
    /// Gets the file's length in bytes.
    /// </summary>
    [JsonNumberHandling(JsonNumberHandling.Strict)]
    public required long Size { get; init; }
}
