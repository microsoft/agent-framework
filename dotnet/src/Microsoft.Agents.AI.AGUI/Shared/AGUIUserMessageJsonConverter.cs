// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class AGUIUserMessageJsonConverter : JsonConverter<AGUIUserMessage>
{
    public override AGUIUserMessage? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        var jsonElementTypeInfo = options.GetTypeInfo(typeof(JsonElement));
        JsonElement jsonElement = (JsonElement)JsonSerializer.Deserialize(ref reader, jsonElementTypeInfo)!;

        var message = new AGUIUserMessage();

        if (jsonElement.TryGetProperty("id", out JsonElement idElement))
        {
            message.Id = idElement.GetString();
        }

        if (jsonElement.TryGetProperty("role", out JsonElement roleElement))
        {
            string? role = roleElement.GetString();
            if (!string.IsNullOrEmpty(role) &&
                !string.Equals(role, AGUIRoles.User, StringComparison.OrdinalIgnoreCase))
            {
                throw new JsonException("AGUI user message role must be 'user'.");
            }
        }

        if (jsonElement.TryGetProperty("name", out JsonElement nameElement))
        {
            message.Name = nameElement.GetString();
        }

        if (!jsonElement.TryGetProperty("content", out JsonElement contentElement))
        {
            throw new JsonException("Missing required property 'content' for AGUIUserMessage deserialization");
        }

        switch (contentElement.ValueKind)
        {
            case JsonValueKind.String:
                message.Content = contentElement.GetString() ?? string.Empty;
                break;
            case JsonValueKind.Array:
                message.InputContents = contentElement.Deserialize(options.GetTypeInfo(typeof(AGUIInputContent[]))) as AGUIInputContent[];
                message.Content = string.Empty;
                break;
            default:
                throw new JsonException("AGUI user message content must be a string or an array.");
        }

        return message;
    }

    public override void Write(Utf8JsonWriter writer, AGUIUserMessage value, JsonSerializerOptions options)
    {
        writer.WriteStartObject();

        if (value.Id is not null)
        {
            writer.WriteString("id", value.Id);
        }

        writer.WriteString("role", AGUIRoles.User);

        if (value.InputContents is { Length: > 0 })
        {
            writer.WritePropertyName("content");
            JsonSerializer.Serialize(writer, value.InputContents, options.GetTypeInfo(typeof(AGUIInputContent[])));
        }
        else
        {
            writer.WriteString("content", value.Content);
        }

        if (value.Name is not null)
        {
            writer.WriteString("name", value.Name);
        }

        writer.WriteEndObject();
    }
}
