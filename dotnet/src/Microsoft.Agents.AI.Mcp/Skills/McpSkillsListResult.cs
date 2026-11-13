// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;
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

    /// <summary>
    /// Gets the declared cache scope, or null when the response's cacheScope field is missing or null.
    /// </summary>
    [JsonPropertyName("cacheScope")]
    [JsonConverter(typeof(McpSkillCacheScopeConverter))]
    public CacheScope? CacheScope { get; set; }
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
    /// Gets the skill's advertised frontmatter.
    /// </summary>
    [JsonConverter(typeof(McpSkillFrontmatterConverter))]
    public required McpSkillFrontmatter Frontmatter { get; init; }

    /// <summary>
    /// Gets the complete file list with expected sizes and hashes, or an indication that no list is provided.
    /// </summary>
    /// <remarks>
    /// <para>
    /// A <see cref="McpSkillManifestResources"/> comes from a JSON array listing every file, including
    /// <c>SKILL.md</c>. Reads are limited to those files, and their content is checked against the listed sizes and hashes.
    /// </para>
    /// <para>
    /// A <see cref="McpSkillDynamicResources"/> comes from the JSON string <c>"dynamic"</c>.
    /// It provides no file list or hashes. Instructions are read from <see cref="Uri"/>, and supporting files
    /// are requested by relative path within the skill's directory.
    /// </para>
    /// <para>
    /// Neither form contains file content or causes files to be fetched during discovery.
    /// Files are read only when needed.
    /// </para>
    /// </remarks>
    [JsonConverter(typeof(McpSkillResourcesConverter))]
    public required McpSkillResources Resources { get; init; }
}

/// <summary>
/// The frontmatter advertised by <c>skills/list</c> or <c>skills/get</c>.
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

    /// <summary>
    /// Gets an optional license name or reference.
    /// </summary>
    public string? License { get; init; }

    /// <summary>
    /// Gets optional compatibility information, validated during discovery.
    /// </summary>
    public string? Compatibility { get; init; }

    /// <summary>
    /// Gets optional custom metadata.
    /// </summary>
    public AdditionalPropertiesDictionary? Metadata { get; init; }

    /// <summary>
    /// Gets or sets the complete JSON snapshot captured when deserializing a skill entry.
    /// </summary>
    [JsonIgnore]
    internal JsonElement OriginalJson { get; set; }
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
