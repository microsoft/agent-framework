// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents.A2A;

internal sealed class LongRunContinuationToken
{
    public LongRunContinuationToken(string taskId)
    {
        this.TaskId = taskId;
    }

    public string TaskId { get; set; }

    public static LongRunContinuationToken Deserialize(string json)
    {
        json = Throw.IfNullOrEmpty(json);

        var token = JsonSerializer.Deserialize<LongRunContinuationToken>(json, A2AJsonContext.Default.LongRunContinuationToken)
            ?? throw new InvalidOperationException("Failed to deserialize LongRunContinuationToken.");

        return token;
    }

    public string Serialize()
    {
        return JsonSerializer.Serialize(this, A2AJsonContext.Default.LongRunContinuationToken);
    }
}
