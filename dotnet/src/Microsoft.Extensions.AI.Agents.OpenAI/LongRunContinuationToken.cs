// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.Text.Json;

namespace Microsoft.Extensions.AI;

internal sealed class LongRunContinuationToken : ContinuationToken
{
    public LongRunContinuationToken(string responseId)
    {
        this.ResponseId = responseId;
    }

    public string ResponseId { get; set; }

    public int? SequenceNumber { get; set; }

    public static LongRunContinuationToken FromToken(ContinuationToken token)
    {
        if (token is LongRunContinuationToken longRunContinuationToken)
        {
            return longRunContinuationToken;
        }

        BinaryData data = token.ToBytes();

        if (data.ToMemory().Length == 0)
        {
            throw new ArgumentException("Failed to create LongRunContinuationToken from provided token.", nameof(token));
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
}
