// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI;

/// <summary>
/// Custom JSON converter for <see cref="AgentSessionStateBagValue"/> that serializes and deserializes
/// the <see cref="AgentSessionStateBagValue.JsonValue"/> directly rather than wrapping it in a container object.
/// </summary>
internal sealed class AgentSessionStateBagValueJsonConverter : JsonConverter<AgentSessionStateBagValue>
{
    /// <inheritdoc/>
    public override AgentSessionStateBagValue Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        var element = JsonElement.ParseValue(ref reader);
        return new AgentSessionStateBagValue(element);
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, AgentSessionStateBagValue value, JsonSerializerOptions options)
    {
        value.JsonValue.WriteTo(writer);
    }
}
