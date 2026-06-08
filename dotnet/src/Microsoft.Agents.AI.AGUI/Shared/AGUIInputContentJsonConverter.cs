// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class AGUIInputContentJsonConverter : JsonConverter<AGUIInputContent>
{
    private const string TypeDiscriminatorPropertyName = "type";

    public override bool CanConvert(Type typeToConvert) =>
        typeof(AGUIInputContent).IsAssignableFrom(typeToConvert);

    public override AGUIInputContent Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        var jsonElementTypeInfo = options.GetTypeInfo(typeof(JsonElement));
        JsonElement jsonElement = (JsonElement)JsonSerializer.Deserialize(ref reader, jsonElementTypeInfo)!;

        if (!jsonElement.TryGetProperty(TypeDiscriminatorPropertyName, out JsonElement discriminatorElement))
        {
            throw new JsonException($"Missing required property '{TypeDiscriminatorPropertyName}' for AGUIInputContent deserialization");
        }

        string? discriminator = discriminatorElement.GetString();

        AGUIInputContent? result = discriminator switch
        {
            "text" => jsonElement.Deserialize(options.GetTypeInfo(typeof(AGUITextInputContent))) as AGUITextInputContent,
            "binary" => DeserializeBinaryInputContent(jsonElement, options),
            _ => throw new JsonException($"Unknown AGUIInputContent type discriminator: '{discriminator}'")
        };

        if (result is null)
        {
            throw new JsonException($"Failed to deserialize AGUIInputContent with type discriminator: '{discriminator}'");
        }

        return result;
    }

    public override void Write(Utf8JsonWriter writer, AGUIInputContent value, JsonSerializerOptions options)
    {
        switch (value)
        {
            case AGUITextInputContent text:
                JsonSerializer.Serialize(writer, text, options.GetTypeInfo(typeof(AGUITextInputContent)));
                break;
            case AGUIBinaryInputContent binary:
                JsonSerializer.Serialize(writer, binary, options.GetTypeInfo(typeof(AGUIBinaryInputContent)));
                break;
            default:
                throw new JsonException($"Unknown AGUIInputContent type: {value.GetType().Name}");
        }
    }

    private static AGUIBinaryInputContent? DeserializeBinaryInputContent(JsonElement jsonElement, JsonSerializerOptions options)
    {
        AGUIBinaryInputContent? binaryContent = jsonElement.Deserialize(options.GetTypeInfo(typeof(AGUIBinaryInputContent))) as AGUIBinaryInputContent;
        if (binaryContent is null)
        {
            return null;
        }

        if (string.IsNullOrEmpty(binaryContent.Id) &&
            string.IsNullOrEmpty(binaryContent.Url) &&
            string.IsNullOrEmpty(binaryContent.Data))
        {
            throw new JsonException("Binary input content must provide at least one of 'id', 'url', or 'data'.");
        }

        return binaryContent;
    }
}
