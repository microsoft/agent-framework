// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI;

internal sealed class LongRunContinuationToken
{
    public LongRunContinuationToken(string responseId)
    {
        this.ResponseId = responseId;
    }

    public string ResponseId { get; set; }

    public int? SequenceNumber { get; set; }

    public static LongRunContinuationToken Deserialize(string json)
    {
        json = Throw.IfNullOrEmpty(json);

        var token = JsonSerializer.Deserialize<LongRunContinuationToken>(json, OpenAIJsonContext2.Default.LongRunContinuationToken)
            ?? throw new InvalidOperationException("Failed to deserialize LongRunContinuationToken.");

        return token;
    }

    public string Serialize()
    {
        return JsonSerializer.Serialize(this, OpenAIJsonContext2.Default.LongRunContinuationToken);
    }
}
