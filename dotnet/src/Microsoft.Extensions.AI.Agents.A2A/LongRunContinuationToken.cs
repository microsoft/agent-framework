// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.Text.Json;

namespace Microsoft.Extensions.AI.Agents.A2A;

internal sealed class LongRunContinuationToken : ContinuationToken
{
    public LongRunContinuationToken(string taskId)
    {
        this.TaskId = taskId;
    }

    public string TaskId { get; set; }

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

        string taskId = null!;

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
                case "taskId":
                    reader.Read();
                    taskId = reader.GetString()!;
                    break;
                default:
                    throw new JsonException($"Unrecognized property '{propertyName}'.");
            }
        }

        return new(taskId);
    }
}
