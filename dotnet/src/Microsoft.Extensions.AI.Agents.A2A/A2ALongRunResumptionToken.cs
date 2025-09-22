// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Text.Json;

namespace Microsoft.Extensions.AI.Agents.A2A;

internal sealed class A2ALongRunResumptionToken : ResumptionToken
{
    internal A2ALongRunResumptionToken(string taskId)
    {
        this.TaskId = taskId;
    }

    internal string TaskId { get; set; }

    internal static A2ALongRunResumptionToken FromToken(ResumptionToken token)
    {
        if (token is A2ALongRunResumptionToken longRunContinuationToken)
        {
            return longRunContinuationToken;
        }

        byte[] data = token.ToBytes();

        if (data.Length == 0)
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

    public override byte[] ToBytes()
    {
        using MemoryStream stream = new();
        using Utf8JsonWriter writer = new(stream);

        writer.WriteStartObject();

        writer.WriteString("taskId", this.TaskId);

        writer.WriteEndObject();

        writer.Flush();
        stream.Position = 0;

        return stream.ToArray();
    }
}
