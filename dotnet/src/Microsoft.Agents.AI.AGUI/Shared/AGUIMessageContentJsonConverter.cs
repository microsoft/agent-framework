// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

#if ASPNETCORE
namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.Shared;
#else
namespace Microsoft.Agents.AI.AGUI.Shared;
#endif

internal sealed class AGUIMessageContentJsonConverter : JsonConverter<AGUIMessageContent>
{
    public override AGUIMessageContent Read(
        ref Utf8JsonReader reader,
        Type typeToConvert,
        JsonSerializerOptions options)
    {
        switch (reader.TokenType)
        {
            case JsonTokenType.String:
                return reader.GetString() ?? string.Empty;

            case JsonTokenType.StartArray:
                var contentArray = JsonSerializer.Deserialize(ref reader, options.GetTypeInfo(typeof(AGUIMessageContentBlock[]))) as AGUIMessageContentBlock[];
                return new AGUIMessageContent(contentArray ?? Array.Empty<AGUIMessageContentBlock>());

            default:
                throw new JsonException("Invalid AGUI message content format. Expected string or array.");
        }
    }

    public override void Write(
        Utf8JsonWriter writer,
        AGUIMessageContent value,
        JsonSerializerOptions options)
    {
        if (value.IsText)
        {
            writer.WriteStringValue(value.ToString());
            return;
        }

        JsonSerializer.Serialize(writer, value.Blocks ?? [], options.GetTypeInfo(typeof(AGUIMessageContentBlock[])));
    }
}
