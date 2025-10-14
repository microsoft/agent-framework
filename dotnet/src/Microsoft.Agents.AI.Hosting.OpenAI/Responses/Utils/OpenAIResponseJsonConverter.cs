// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Utils;

internal sealed class OpenAIResponseJsonConverter : JsonConverter<OpenAIResponse>
{
    public override OpenAIResponse? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        var item = OpenAIResponsesModelFactory.OpenAIResponse();
        var jsonModel = item as IJsonModel<OpenAIResponse>;
        Debug.Assert(jsonModel is not null, "OpenAIResponse should implement IJsonModel<OpenAIResponse>");

        return jsonModel.Create(ref reader, ModelReaderWriterOptions.Json);
    }

    public override void Write(Utf8JsonWriter writer, OpenAIResponse value, JsonSerializerOptions options)
    {
        var jsonModel = value as IJsonModel<OpenAIResponse>;
        Debug.Assert(jsonModel is not null, "OpenAIResponse should implement IJsonModel<OpenAIResponse>");

        jsonModel.Write(writer, ModelReaderWriterOptions.Json);
    }
}
