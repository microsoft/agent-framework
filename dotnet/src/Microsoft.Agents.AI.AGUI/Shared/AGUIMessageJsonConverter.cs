// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class AGUIMessageJsonConverter : JsonConverter<AGUIMessage>
{
    private const string RoleDiscriminatorPropertyName = "role";

    public override bool CanConvert(Type typeToConvert) =>
        typeof(AGUIMessage).IsAssignableFrom(typeToConvert);

    public override AGUIMessage Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options)
    {
        var jsonElementTypeInfo = options.GetTypeInfo(typeof(JsonElement));
        JsonElement jsonElement = (JsonElement)JsonSerializer.Deserialize(ref reader, jsonElementTypeInfo)!;

        // Try to get the discriminator property
        if (!jsonElement.TryGetProperty(RoleDiscriminatorPropertyName, out JsonElement discriminatorElement))
        {
            throw new JsonException($"Missing required property '{RoleDiscriminatorPropertyName}' for AGUIMessage deserialization");
        }

        string? discriminator = discriminatorElement.GetString();

        // Map discriminator to concrete type and deserialize using type info from options
        AGUIMessage? result = discriminator switch
        {
            AGUIRoles.Developer => jsonElement.Deserialize(options.GetTypeInfo(typeof(AGUIDeveloperMessage))) as AGUIDeveloperMessage,
            AGUIRoles.System => jsonElement.Deserialize(options.GetTypeInfo(typeof(AGUISystemMessage))) as AGUISystemMessage,
            AGUIRoles.User => jsonElement.Deserialize(options.GetTypeInfo(typeof(AGUIUserMessage))) as AGUIUserMessage,
            AGUIRoles.Assistant => jsonElement.Deserialize(options.GetTypeInfo(typeof(AGUIAssistantMessage))) as AGUIAssistantMessage,
            AGUIRoles.Tool => jsonElement.Deserialize(options.GetTypeInfo(typeof(AGUIToolMessage))) as AGUIToolMessage,
            _ => throw new JsonException($"Unknown AGUIMessage role discriminator: '{discriminator}'")
        };

        if (result == null)
        {
            throw new JsonException($"Failed to deserialize AGUIMessage with role discriminator: '{discriminator}'");
        }

        return result;
    }

    public override void Write(
        Utf8JsonWriter writer,
        AGUIMessage value,
        JsonSerializerOptions options)
    {
        // Serialize the concrete type directly using type info from options
        switch (value)
        {
            case AGUIDeveloperMessage developer:
                JsonSerializer.Serialize(writer, developer, options.GetTypeInfo(typeof(AGUIDeveloperMessage)));
                break;
            case AGUISystemMessage system:
                JsonSerializer.Serialize(writer, system, options.GetTypeInfo(typeof(AGUISystemMessage)));
                break;
            case AGUIUserMessage user:
                JsonSerializer.Serialize(writer, user, options.GetTypeInfo(typeof(AGUIUserMessage)));
                break;
            case AGUIAssistantMessage assistant:
                JsonSerializer.Serialize(writer, assistant, options.GetTypeInfo(typeof(AGUIAssistantMessage)));
                break;
            case AGUIToolMessage tool:
                JsonSerializer.Serialize(writer, tool, options.GetTypeInfo(typeof(AGUIToolMessage)));
                break;
            default:
                throw new JsonException($"Unknown AGUIMessage type: {value.GetType().Name}");
        }
    }
}
