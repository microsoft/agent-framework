// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Extensions.AI;

internal sealed class ResponsesLongRunResumptionToken : ResumptionToken
{
    internal ResponsesLongRunResumptionToken(string responseId)
    {
        this.ResponseId = responseId;
    }

    internal string ResponseId { get; set; }

    internal int? SequenceNumber { get; set; }

    internal static ResponsesLongRunResumptionToken FromToken(ResumptionToken token)
    {
        if (token is ResponsesLongRunResumptionToken longRunResumptionToken)
        {
            return longRunResumptionToken;
        }

        byte[] data = token.ToBytes();

        if (data.Length == 0)
        {
            throw new ArgumentException("Failed to create LongRunResumptionToken from provided token.", nameof(token));
        }

        Utf8JsonReader reader = new(data);

        string responseId = null!;
        int? startAfter = null;

        reader.Read();

        while (reader.Read())
        {
            if (reader.TokenType == JsonTokenType.EndObject)
            {
                break;
            }

            string propertyName = reader.GetString()!;

            switch (propertyName)
            {
                case "responseId":
                    reader.Read();
                    responseId = reader.GetString()!;
                    break;
                case "sequenceNumber":
                    reader.Read();
                    startAfter = reader.GetInt32();
                    break;
                default:
                    throw new JsonException($"Unrecognized property '{propertyName}'.");
            }
        }

        return new(responseId)
        {
            SequenceNumber = startAfter
        };
    }

    public override byte[] ToBytes()
    {
        using MemoryStream stream = new();
        using Utf8JsonWriter writer = new(stream);

        writer.WriteStartObject();

        writer.WriteString("responseId", this.ResponseId);

        if (this.SequenceNumber.HasValue)
        {
            writer.WriteNumber("sequenceNumber", this.SequenceNumber.Value);
        }

        writer.WriteEndObject();

        writer.Flush();
        stream.Position = 0;

        return stream.ToArray();
    }
}
