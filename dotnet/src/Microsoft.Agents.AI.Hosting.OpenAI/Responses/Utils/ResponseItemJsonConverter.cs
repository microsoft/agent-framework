// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Utils;

internal sealed class ResponseItemJsonConverter : JsonConverter<ResponseItem?>
{
    public override ResponseItem? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        var item = ResponseItem.CreateUserMessageItem(""); // no other way to instantiate it.
        var jsonModel = item as IJsonModel<ResponseItem>;
        Debug.Assert(jsonModel is not null, "ResponseItem should implement IJsonModel<ResponseItem>");
        return jsonModel.Create(ref reader, ModelReaderWriterOptions.Json);
    }

    public override void Write(Utf8JsonWriter writer, ResponseItem? value, JsonSerializerOptions options)
    {
        if (value is null)
        {
            writer.WriteNullValue();
            return;
        }

        var jsonmodel = value as IJsonModel<ResponseItem>;
        Debug.Assert(jsonmodel is not null, "ResponseItem should implement IJsonModel<ResponseItem>");
        jsonmodel.Write(writer, ModelReaderWriterOptions.Json);
    }
}
