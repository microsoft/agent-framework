// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI;

/// <summary>
/// Converts server-provided skill metadata without discarding unrecognized fields.
/// </summary>
/// <remarks>
/// Reads known fields into <see cref="McpSkillFrontmatter"/> and saves the complete metadata
/// in <see cref="McpSkillFrontmatter.OriginalJson"/>. Serialization writes the saved JSON rather than
/// rebuilding it from those fields.
/// </remarks>
internal sealed class McpSkillFrontmatterConverter : JsonConverter<McpSkillFrontmatter>
{
    /// <inheritdoc/>
    public override McpSkillFrontmatter Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        using JsonDocument document = JsonDocument.ParseValue(ref reader);

        // The converter applies to the entry property, so this uses the generated converter without recursion.
        McpSkillFrontmatter frontmatter = document.RootElement.Deserialize(McpSkillsJsonContext.Default.McpSkillFrontmatter)
            ?? throw new JsonException("Skill frontmatter must not be null.");

        frontmatter.OriginalJson = document.RootElement.Clone();

        return frontmatter;
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, McpSkillFrontmatter value, JsonSerializerOptions options)
    {
        if (value.OriginalJson.ValueKind != JsonValueKind.Object)
        {
            throw new JsonException("Skill frontmatter must have an original JSON object snapshot.");
        }

        value.OriginalJson.WriteTo(writer);
    }
}
