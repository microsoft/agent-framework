// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.A2A;
#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
internal class A2AContinuationToken : ResponseContinuationToken
{
    internal A2AContinuationToken(string taskId)
    {
        _ = Throw.IfNullOrEmpty(taskId);

        this.TaskId = taskId;
    }

    internal string TaskId { get; }

    internal static A2AContinuationToken FromToken(ResponseContinuationToken token)
    {
        if (token is A2AContinuationToken longRunContinuationToken)
        {
            return longRunContinuationToken;
        }

        ReadOnlyMemory<byte> data = token.ToBytes();

        if (data.Length == 0)
        {
            Throw.ArgumentException(nameof(token), "Failed to create A2AContinuationToken from provided token because it does not contain any data.");
        }

        Utf8JsonReader reader = new(data.Span);

        string taskId = null!;

        reader.Read();

        while (reader.Read())
        {
            if (reader.TokenType == JsonTokenType.EndObject)
            {
                break;
            }

            string propertyName = reader.GetString() ?? throw new JsonException("Failed to read property name from continuation token.");

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

    public override ReadOnlyMemory<byte> ToBytes()
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
