// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

/// <summary>
/// Custom JSON converter for polymorphic deserialization of AGUIMessage and its derived types.
/// Uses the "role" property as a discriminator to determine the concrete type to deserialize.
/// </summary>
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
        // Parse the JSON into a JsonDocument to inspect properties
        using JsonDocument document = JsonDocument.ParseValue(ref reader);
        JsonElement jsonElement = document.RootElement.Clone();

        // Try to get the discriminator property
        if (!jsonElement.TryGetProperty(RoleDiscriminatorPropertyName, out JsonElement discriminatorElement))
        {
            throw new JsonException($"Missing required property '{RoleDiscriminatorPropertyName}' for AGUIMessage deserialization");
        }

        string? discriminator = discriminatorElement.GetString();

#if ASPNETCORE
        AGUIJsonSerializerContext context = (AGUIJsonSerializerContext)options.TypeInfoResolver!;
#else
        AGUIJsonSerializerContext context = AGUIJsonSerializerContext.Default;
#endif

        // Map discriminator to concrete type and deserialize using the serializer context
        AGUIMessage? result = discriminator switch
        {
            AGUIRoles.Developer => jsonElement.Deserialize(context.AGUIDeveloperMessage),
            AGUIRoles.System => jsonElement.Deserialize(context.AGUISystemMessage),
            AGUIRoles.User => jsonElement.Deserialize(context.AGUIUserMessage),
            AGUIRoles.Assistant => jsonElement.Deserialize(context.AGUIAssistantMessage),
            AGUIRoles.Tool => jsonElement.Deserialize(context.AGUIToolMessage),
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
#if ASPNETCORE
        AGUIJsonSerializerContext context = (AGUIJsonSerializerContext)options.TypeInfoResolver!;
#else
        AGUIJsonSerializerContext context = AGUIJsonSerializerContext.Default;
#endif

        // Serialize the concrete type directly using the serializer context
        switch (value)
        {
            case AGUIDeveloperMessage developer:
                JsonSerializer.Serialize(writer, developer, context.AGUIDeveloperMessage);
                break;
            case AGUISystemMessage system:
                JsonSerializer.Serialize(writer, system, context.AGUISystemMessage);
                break;
            case AGUIUserMessage user:
                JsonSerializer.Serialize(writer, user, context.AGUIUserMessage);
                break;
            case AGUIAssistantMessage assistant:
                JsonSerializer.Serialize(writer, assistant, context.AGUIAssistantMessage);
                break;
            case AGUIToolMessage tool:
                JsonSerializer.Serialize(writer, tool, context.AGUIToolMessage);
                break;
            default:
                throw new JsonException($"Unknown AGUIMessage type: {value.GetType().Name}");
        }
    }
}
