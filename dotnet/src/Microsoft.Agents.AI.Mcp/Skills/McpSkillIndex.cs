// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI;

/// <summary>
/// DTO for the skill discovery index document served at <c>skill://index.json</c>.
/// </summary>
/// <remarks>
/// <para>
/// Schema reference: <see href="https://schemas.agentskills.io/discovery/0.2.0/schema.json"/>
/// (Agent Skills Discovery v0.2.0), as used by the legacy SEP-2640 MCP index binding.
/// The <c>url</c> field contains a full MCP resource URI. Unlike the base schema, the
/// <c>digest</c> field is optional; supplied archive digests are verified in addition to
/// relying on the authenticated MCP transport.
/// </para>
/// <para>
/// All properties are nullable so that deserialization succeeds even when the server-side index
/// is incomplete or malformed; callers MUST validate required fields before use.
/// </para>
/// </remarks>
internal sealed class McpSkillIndex
{
    /// <summary>
    /// Gets or sets the opaque schema identifier URI. Required by the base schema; clients SHOULD
    /// match this against known schema URIs (e.g.
    /// <c>https://schemas.agentskills.io/discovery/0.2.0/schema.json</c>) before processing the index.
    /// </summary>
    [JsonPropertyName("$schema")]
    public string? Schema { get; set; }

    /// <summary>
    /// Gets or sets the array of skill entries. Required by the schema; an empty or missing
    /// <c>skills</c> array means the index advertises no skills.
    /// </summary>
    [JsonPropertyName("skills")]
    public List<McpSkillIndexEntry>? Skills { get; set; }
}

/// <summary>
/// A single entry in the skill discovery index.
/// </summary>
/// <remarks>
/// Field requirements per the v0.2.0 schema and the SEP-2640 binding:
/// <list type="bullet">
///   <item><description><c>type</c>, <c>description</c>, and <c>url</c> are REQUIRED.</description></item>
///   <item><description><c>name</c> is REQUIRED for <c>skill-md</c> and <c>archive</c> entries; OMITTED for <c>mcp-resource-template</c>.</description></item>
///   <item><description><c>digest</c> is optional under this MCP index binding; supplied archive digests are verified before extraction.</description></item>
/// </list>
/// All properties are nullable to keep deserialization lenient; callers validate required fields before use.
/// </remarks>
internal sealed class McpSkillIndexEntry
{
    /// <summary>
    /// Gets or sets the skill name (1-64 chars, lowercase alphanumeric and hyphens; no leading,
    /// trailing, or consecutive hyphens). Required for <c>skill-md</c> and <c>archive</c> entries;
    /// omitted for <c>mcp-resource-template</c>.
    /// </summary>
    [JsonPropertyName("name")]
    public string? Name { get; set; }

    /// <summary>
    /// Gets or sets the entry distribution type. Required. Schema-defined values are
    /// <c>skill-md</c> and <c>archive</c>; the SEP-2640 MCP binding additionally defines
    /// <c>mcp-resource-template</c>.
    /// </summary>
    [JsonPropertyName("type")]
    public string? Type { get; set; }

    /// <summary>
    /// Gets or sets the skill description (max 1024 chars per the Agent Skills specification).
    /// Required. For <c>skill-md</c> entries, SHOULD match the <c>description</c> in the skill's
    /// <c>SKILL.md</c> frontmatter.
    /// </summary>
    [JsonPropertyName("description")]
    public string? Description { get; set; }

    /// <summary>
    /// Gets or sets the artifact URL. Required. For <c>skill-md</c>, points at the
    /// <c>SKILL.md</c> resource. For <c>archive</c>, points at the archive file. For
    /// <c>mcp-resource-template</c>, an RFC 6570 URI template that resolves to a <c>SKILL.md</c>
    /// resource URI.
    /// </summary>
    [JsonPropertyName("url")]
    public string? Url { get; set; }

    /// <summary>
    /// Gets or sets the SHA-256 digest of the artifact bytes, formatted as <c>sha256:</c> followed
    /// by 64 lowercase hexadecimal characters. Required by the base v0.2.0 schema but optional
    /// under this MCP index binding. Supplied archive digests are verified before extraction;
    /// verification does not apply to <c>skill-md</c> entries.
    /// </summary>
    [JsonPropertyName("digest")]
    public string? Digest { get; set; }
}
