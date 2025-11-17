// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

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
        var jsonElementTypeInfo = options.GetTypeInfo(typeof(JsonElement));
        JsonElement jsonElement = (JsonElement)JsonSerializer.Deserialize(ref reader, jsonElementTypeInfo)!;

        // Try to get the discriminator property
        if (!jsonElement.TryGetProperty(TypeDiscriminatorPropertyName, out JsonElement discriminatorElement))
        {
            throw new JsonException($"Missing required property '{TypeDiscriminatorPropertyName}' for BaseEvent deserialization");
        }

        string? discriminator = discriminatorElement.GetString();

        // Map discriminator to concrete type and deserialize using type info from options
        BaseEvent? result = discriminator switch
        {
            AGUIEventTypes.RunStarted => jsonElement.Deserialize(options.GetTypeInfo(typeof(RunStartedEvent))) as RunStartedEvent,
            AGUIEventTypes.RunFinished => jsonElement.Deserialize(options.GetTypeInfo(typeof(RunFinishedEvent))) as RunFinishedEvent,
            AGUIEventTypes.RunError => jsonElement.Deserialize(options.GetTypeInfo(typeof(RunErrorEvent))) as RunErrorEvent,
            AGUIEventTypes.TextMessageStart => jsonElement.Deserialize(options.GetTypeInfo(typeof(TextMessageStartEvent))) as TextMessageStartEvent,
            AGUIEventTypes.TextMessageContent => jsonElement.Deserialize(options.GetTypeInfo(typeof(TextMessageContentEvent))) as TextMessageContentEvent,
            AGUIEventTypes.TextMessageEnd => jsonElement.Deserialize(options.GetTypeInfo(typeof(TextMessageEndEvent))) as TextMessageEndEvent,
            AGUIEventTypes.ToolCallStart => jsonElement.Deserialize(options.GetTypeInfo(typeof(ToolCallStartEvent))) as ToolCallStartEvent,
            AGUIEventTypes.ToolCallArgs => jsonElement.Deserialize(options.GetTypeInfo(typeof(ToolCallArgsEvent))) as ToolCallArgsEvent,
            AGUIEventTypes.ToolCallEnd => jsonElement.Deserialize(options.GetTypeInfo(typeof(ToolCallEndEvent))) as ToolCallEndEvent,
            AGUIEventTypes.ToolCallResult => jsonElement.Deserialize(options.GetTypeInfo(typeof(ToolCallResultEvent))) as ToolCallResultEvent,
            AGUIEventTypes.StateSnapshot => jsonElement.Deserialize(options.GetTypeInfo(typeof(StateSnapshotEvent))) as StateSnapshotEvent,
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
        // Serialize the concrete type directly using type info from options
        switch (value)
        {
            case RunStartedEvent runStarted:
                JsonSerializer.Serialize(writer, runStarted, options.GetTypeInfo(typeof(RunStartedEvent)));
                break;
            case RunFinishedEvent runFinished:
                JsonSerializer.Serialize(writer, runFinished, options.GetTypeInfo(typeof(RunFinishedEvent)));
                break;
            case RunErrorEvent runError:
                JsonSerializer.Serialize(writer, runError, options.GetTypeInfo(typeof(RunErrorEvent)));
                break;
            case TextMessageStartEvent textStart:
                JsonSerializer.Serialize(writer, textStart, options.GetTypeInfo(typeof(TextMessageStartEvent)));
                break;
            case TextMessageContentEvent textContent:
                JsonSerializer.Serialize(writer, textContent, options.GetTypeInfo(typeof(TextMessageContentEvent)));
                break;
            case TextMessageEndEvent textEnd:
                JsonSerializer.Serialize(writer, textEnd, options.GetTypeInfo(typeof(TextMessageEndEvent)));
                break;
            case ToolCallStartEvent toolCallStart:
                JsonSerializer.Serialize(writer, toolCallStart, options.GetTypeInfo(typeof(ToolCallStartEvent)));
                break;
            case ToolCallArgsEvent toolCallArgs:
                JsonSerializer.Serialize(writer, toolCallArgs, options.GetTypeInfo(typeof(ToolCallArgsEvent)));
                break;
            case ToolCallEndEvent toolCallEnd:
                JsonSerializer.Serialize(writer, toolCallEnd, options.GetTypeInfo(typeof(ToolCallEndEvent)));
                break;
            case ToolCallResultEvent toolCallResult:
                JsonSerializer.Serialize(writer, toolCallResult, options.GetTypeInfo(typeof(ToolCallResultEvent)));
                break;
            case StateSnapshotEvent stateSnapshot:
                JsonSerializer.Serialize(writer, stateSnapshot, options.GetTypeInfo(typeof(StateSnapshotEvent)));
                break;
            case StateDeltaEvent stateDelta:
                JsonSerializer.Serialize(writer, stateDelta, options.GetTypeInfo(typeof(StateDeltaEvent)));
                break;
            default:
                throw new InvalidOperationException($"Unknown event type: {value.GetType().Name}");
        }
    }
}
