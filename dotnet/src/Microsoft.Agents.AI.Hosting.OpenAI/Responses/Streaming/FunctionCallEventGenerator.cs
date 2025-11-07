// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Streaming;

/// <summary>
/// A generator for streaming events from function call content.
/// </summary>
internal sealed class FunctionCallEventGenerator(
        IdGenerator idGenerator,
        SequenceNumber seq,
        int outputIndex,
        JsonSerializerOptions jsonSerializerOptions) : StreamingEventGenerator
{
    public override bool IsSupported(AIContent content) => content is FunctionCallContent;

    public override IEnumerable<StreamingResponseEvent> ProcessContent(AIContent content)
    {
        if (content is not FunctionCallContent functionCallContent)
        {
            throw new InvalidOperationException("FunctionCallEventGenerator only supports FunctionCallContent.");
        }

        var item = functionCallContent.ToFunctionToolCallItemResource(idGenerator.GenerateFunctionCallId(), jsonSerializerOptions);
        yield return new StreamingOutputItemAdded
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            Item = item
        };

        yield return new StreamingFunctionCallArgumentsDelta
        {
            SequenceNumber = seq.Increment(),
            ItemId = item.Id,
            OutputIndex = outputIndex,
            Delta = item.Arguments
        };

        yield return new StreamingFunctionCallArgumentsDone
        {
            SequenceNumber = seq.Increment(),
            ItemId = item.Id,
            OutputIndex = outputIndex,
            Arguments = item.Arguments
        };

        yield return new StreamingOutputItemDone
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            Item = item
        };
    }

    public override IEnumerable<StreamingResponseEvent> Complete() => [];
}
