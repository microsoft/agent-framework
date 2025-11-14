// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Streaming;

/// <summary>
/// A generator for streaming events from audio content.
/// </summary>
internal sealed class AudioContentEventGenerator(
        IdGenerator idGenerator,
        SequenceNumber seq,
        int outputIndex) : StreamingEventGenerator
{
    public override bool IsSupported(AIContent content) =>
        content is DataContent dataContent && dataContent.HasTopLevelMediaType("audio");

    public override IEnumerable<StreamingResponseEvent> ProcessContent(AIContent content)
    {
        if (content is not DataContent audioData || !audioData.HasTopLevelMediaType("audio"))
        {
            throw new InvalidOperationException("AudioContentEventGenerator only supports audio DataContent.");
        }

        var itemId = idGenerator.GenerateMessageId();
        if (ItemContentConverter.ToItemContent(content) is not ItemContentInputAudio itemContent)
        {
            throw new InvalidOperationException("Failed to convert audio content to ItemContentInputAudio.");
        }

        var item = new ResponsesAssistantMessageItemResource
        {
            Id = itemId,
            Status = ResponsesMessageItemResourceStatus.Completed,
            Content = [itemContent]
        };

        yield return new StreamingOutputItemAdded
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            Item = item
        };

        yield return new StreamingContentPartAdded
        {
            SequenceNumber = seq.Increment(),
            ItemId = itemId,
            OutputIndex = outputIndex,
            ContentIndex = 0,
            Part = itemContent
        };

        yield return new StreamingContentPartDone
        {
            SequenceNumber = seq.Increment(),
            ItemId = itemId,
            OutputIndex = outputIndex,
            ContentIndex = 0,
            Part = itemContent
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
