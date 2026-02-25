// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI;

/// <summary>
/// Custom JSON converter for <see cref="AgentSessionStateBag"/> that serializes and deserializes
/// the internal dictionary contents rather than the container object's public properties.
/// </summary>
public sealed class AgentSessionStateBagJsonConverter : JsonConverter<AgentSessionStateBag>
{
    /// <inheritdoc/>
    public override AgentSessionStateBag Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        var element = JsonElement.ParseValue(ref reader);
        return AgentSessionStateBag.Deserialize(element);
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, AgentSessionStateBag value, JsonSerializerOptions options)
    {
        var element = value.Serialize();
        element.WriteTo(writer);
    }
}
