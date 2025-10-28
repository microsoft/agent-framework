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
/// Custom JSON converter for polymorphic deserialization of BaseEvent and its derived types.
/// Uses the "type" property as a discriminator to determine the concrete type to deserialize.
/// </summary>
internal sealed class BaseEventJsonConverter : JsonConverter<BaseEvent>
{
    private const string TypeDiscriminatorPropertyName = "type";

    public override bool CanConvert(Type typeToConvert) =>
        typeof(BaseEvent).IsAssignableFrom(typeToConvert);

    public override BaseEvent Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options)
    {
        // Parse the JSON into a JsonDocument to inspect properties
        using JsonDocument document = JsonDocument.ParseValue(ref reader);
        JsonElement jsonElement = document.RootElement.Clone();

        // Try to get the discriminator property
        if (!jsonElement.TryGetProperty(TypeDiscriminatorPropertyName, out JsonElement discriminatorElement))
        {
            throw new JsonException($"Missing required property '{TypeDiscriminatorPropertyName}' for BaseEvent deserialization");
        }

        string? discriminator = discriminatorElement.GetString();

#if ASPNETCORE
        AGUIJsonSerializerContext context = (AGUIJsonSerializerContext)options.TypeInfoResolver!;
#else
        AGUIJsonSerializerContext context = AGUIJsonSerializerContext.Default;
#endif

        // Map discriminator to concrete type and deserialize using the serializer context
        BaseEvent? result = discriminator switch
        {
            AGUIEventTypes.RunStarted => jsonElement.Deserialize(context.RunStartedEvent),
            AGUIEventTypes.RunFinished => jsonElement.Deserialize(context.RunFinishedEvent),
            AGUIEventTypes.RunError => jsonElement.Deserialize(context.RunErrorEvent),
            AGUIEventTypes.TextMessageStart => jsonElement.Deserialize(context.TextMessageStartEvent),
            AGUIEventTypes.TextMessageContent => jsonElement.Deserialize(context.TextMessageContentEvent),
            AGUIEventTypes.TextMessageEnd => jsonElement.Deserialize(context.TextMessageEndEvent),
            _ => throw new JsonException($"Unknown BaseEvent type discriminator: '{discriminator}'")
        };

        if (result == null)
        {
            throw new JsonException($"Failed to deserialize BaseEvent with type discriminator: '{discriminator}'");
        }

        return result;
    }

    public override void Write(
        Utf8JsonWriter writer,
        BaseEvent value,
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
            case RunStartedEvent runStarted:
                JsonSerializer.Serialize(writer, runStarted, context.RunStartedEvent);
                break;
            case RunFinishedEvent runFinished:
                JsonSerializer.Serialize(writer, runFinished, context.RunFinishedEvent);
                break;
            case RunErrorEvent runError:
                JsonSerializer.Serialize(writer, runError, context.RunErrorEvent);
                break;
            case TextMessageStartEvent textStart:
                JsonSerializer.Serialize(writer, textStart, context.TextMessageStartEvent);
                break;
            case TextMessageContentEvent textContent:
                JsonSerializer.Serialize(writer, textContent, context.TextMessageContentEvent);
                break;
            case TextMessageEndEvent textEnd:
                JsonSerializer.Serialize(writer, textEnd, context.TextMessageEndEvent);
                break;
            default:
                throw new JsonException($"Unknown BaseEvent type: {value.GetType().Name}");
        }
    }
}
