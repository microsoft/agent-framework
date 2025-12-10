// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.DurableTask.State;

/// <summary>
/// JSON converter for <see cref="DurableAgentState"/> which performs schema version checks before deserialization.
/// </summary>
internal sealed class DurableAgentStateJsonConverter : JsonConverter<DurableAgentState>
{
    private const string SchemaVersionPropertyName = "schemaVersion";
    private const string DataPropertyName = "data";

    /// <inheritdoc/>
    public override DurableAgentState? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        JsonElement? element = JsonSerializer.Deserialize(
            ref reader,
            DurableAgentStateJsonContext.Default.JsonElement);

        if (element is null)
        {
            throw new JsonException("The durable agent state is not valid JSON.");
        }

        if (!element.Value.TryGetProperty(SchemaVersionPropertyName, out JsonElement versionElement))
        {
            throw new InvalidOperationException("The durable agent state is missing the 'schemaVersion' property.");
        }

        if (!Version.TryParse(versionElement.GetString(), out Version? schemaVersion))
        {
            throw new InvalidOperationException("The durable agent state has an invalid 'schemaVersion' property.");
        }

        if (schemaVersion.Major != 1)
        {
            throw new InvalidOperationException($"The durable agent state schema version '{schemaVersion}' is not supported.");
        }

        if (!element.Value.TryGetProperty(DataPropertyName, out JsonElement dataElement))
        {
            throw new InvalidOperationException("The durable agent state is missing the 'data' property.");
        }

        DurableAgentStateData? data = dataElement.Deserialize(
            DurableAgentStateJsonContext.Default.DurableAgentStateData);

        return new DurableAgentState
        {
            SchemaVersion = schemaVersion.ToString(),
            Data = data ?? new DurableAgentStateData()
        };
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, DurableAgentState value, JsonSerializerOptions options)
    {
        writer.WriteStartObject();
        writer.WritePropertyName(SchemaVersionPropertyName);
        writer.WriteStringValue(value.SchemaVersion);
        writer.WritePropertyName(DataPropertyName);
        JsonSerializer.Serialize(
            writer,
            value.Data,
            DurableAgentStateJsonContext.Default.DurableAgentStateData);
        writer.WriteEndObject();
    }
}
