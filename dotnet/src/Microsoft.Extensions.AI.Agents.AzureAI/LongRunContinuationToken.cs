// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel;
using System.Text.Json;
using Microsoft.Shared.Diagnostics;

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

    public static LongRunContinuationToken Deserialize(string json)
    {
        Throw.IfNullOrEmpty(json);

        var token = JsonSerializer.Deserialize<LongRunContinuationToken>(json, JsonContext.Default.LongRunContinuationToken)
            ?? throw new InvalidOperationException("Failed to deserialize LongRunContinuationToken.");

        return token;
    }

    public string Serialize()
    {
        return JsonSerializer.Serialize(this, JsonContext.Default.LongRunContinuationToken);
    }
}
