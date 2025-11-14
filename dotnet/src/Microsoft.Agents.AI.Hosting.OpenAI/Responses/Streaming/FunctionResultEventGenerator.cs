// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Streaming;

/// <summary>
/// A generator for streaming events from function result content.
/// </summary>
internal sealed class FunctionResultEventGenerator(
        IdGenerator idGenerator,
        SequenceNumber seq,
        int outputIndex) : StreamingEventGenerator
{
    public override bool IsSupported(AIContent content) => content is FunctionResultContent;

    public override IEnumerable<StreamingResponseEvent> ProcessContent(AIContent content)
    {
        if (content is not FunctionResultContent functionResultContent)
        {
            throw new InvalidOperationException("FunctionResultEventGenerator only supports FunctionResultContent.");
        }

        var item = functionResultContent.ToFunctionToolCallOutputItemResource(idGenerator.GenerateFunctionOutputId());
        yield return new StreamingOutputItemAdded
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            Item = item
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
