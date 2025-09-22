// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Azure.AI.Agents.Persistent;

internal sealed class PersistentLongRunResumptionToken : ResumptionToken
{
    internal PersistentLongRunResumptionToken(string runId, string threadId)
    {
        this.RunId = runId;
        this.ThreadId = threadId;
    }

    internal string RunId { get; set; }

    internal string ThreadId { get; set; }

    internal string? StepId { get; set; }

    internal static PersistentLongRunResumptionToken FromToken(ResumptionToken token)
    {
        if (token is PersistentLongRunResumptionToken longRunContinuationToken)
        {
            return longRunContinuationToken;
        }

        byte[] data = token.ToBytes();

        if (data.Length == 0)
        {
            throw new ArgumentException("Failed to create LongRunContinuationToken from provided token.", nameof(token));
        }

        Utf8JsonReader reader = new(data);

        string runId = null!;
        string threadId = null!;
        string? stepId = null;

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
                case "runId":
                    reader.Read();
                    runId = reader.GetString()!;
                    break;
                case "threadId":
                    reader.Read();
                    threadId = reader.GetString()!;
                    break;
                case "stepId":
                    reader.Read();
                    stepId = reader.GetString();
                    break;
                default:
                    throw new JsonException($"Unrecognized property '{propertyName}'.");
            }
        }

        return new(runId, threadId)
        {
            StepId = stepId
        };
    }

    public override byte[] ToBytes()
    {
        using MemoryStream stream = new();
        using Utf8JsonWriter writer = new(stream);

        writer.WriteStartObject();

        writer.WriteString("runId", this.RunId);
        writer.WriteString("threadId", this.ThreadId);

        if (this.StepId is not null)
        {
            writer.WriteString("stepId", this.StepId);
        }

        writer.WriteEndObject();

        writer.Flush();
        stream.Position = 0;

        return stream.ToArray();
    }
}
