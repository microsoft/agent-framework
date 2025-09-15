// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.Text.Json;

namespace Azure.AI.Agents.Persistent;

internal sealed class LongRunContinuationToken : ContinuationToken
{
    public LongRunContinuationToken(string runId, string threadId)
    {
        this.RunId = runId;
        this.ThreadId = threadId;
    }

    public string RunId { get; set; }

    public string ThreadId { get; set; }

    public string? StepId { get; set; }

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
}
