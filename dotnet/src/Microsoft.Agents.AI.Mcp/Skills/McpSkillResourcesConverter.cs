// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI;

/// <summary>
/// Reads and writes a skill entry's <c>resources</c> field as a file-list array or the string <c>"dynamic"</c>.
/// </summary>
/// <remarks>
/// <para>
/// An array becomes a <see cref="McpSkillManifestResources"/>, containing each file's URI, expected size,
/// and hash. The exact, case-sensitive string <c>"dynamic"</c> becomes a <see cref="McpSkillDynamicResources"/>,
/// indicating that the server provides no file list or hashes. Writing either type produces the corresponding JSON form.
/// </para>
/// <para>
/// This converter checks the JSON form, not whether the file list is complete or its entries are valid for the skill.
/// The catalog performs those checks before creating a skill. No file content is fetched by this converter.
/// </para>
/// </remarks>
internal sealed class McpSkillResourcesConverter : JsonConverter<McpSkillResources>
{
    /// <inheritdoc/>
    /// <exception cref="JsonException">
    /// The value is not a file-list array or the string <c>"dynamic"</c>, or a file description cannot be read.
    /// </exception>
    public override McpSkillResources Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.String && reader.ValueTextEquals("dynamic"))
        {
            return new McpSkillDynamicResources();
        }

        if (reader.TokenType == JsonTokenType.StartArray)
        {
            return new McpSkillManifestResources(
                JsonSerializer.Deserialize(ref reader, McpSkillsJsonContext.Default.McpSkillResourceEntryArray)
                    ?? throw new JsonException("A resource manifest must not be null."));
        }

        throw new JsonException("Skill resources must be a manifest array or \"dynamic\".");
    }

    /// <inheritdoc/>
    /// <exception cref="JsonException">The resource type is not supported.</exception>
    public override void Write(Utf8JsonWriter writer, McpSkillResources value, JsonSerializerOptions options)
    {
        switch (value)
        {
            case McpSkillDynamicResources:
                writer.WriteStringValue("dynamic");
                break;
            case McpSkillManifestResources manifest:
                writer.WriteStartArray();
                foreach (McpSkillResourceEntry entry in manifest.Entries)
                {
                    JsonSerializer.Serialize(writer, entry, McpSkillsJsonContext.Default.McpSkillResourceEntry);
                }

                writer.WriteEndArray();
                break;
            default:
                throw new JsonException("Unsupported skill resources.");
        }
    }
}
