// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Streaming;

/// <summary>
/// A generator for streaming events from function approval response content.
/// This is a non-standard DevUI extension for human-in-the-loop scenarios.
/// </summary>
internal sealed class ToolApprovalResponseEventGenerator(
        IdGenerator idGenerator,
        SequenceNumber seq,
        int outputIndex) : StreamingEventGenerator
{
    public override bool IsSupported(AIContent content) => content is ToolApprovalResponseContent;

    public override IEnumerable<StreamingResponseEvent> ProcessContent(AIContent content)
    {
        if (content is not ToolApprovalResponseContent approvalResponse)
        {
            throw new InvalidOperationException("ToolApprovalResponseEventGenerator only supports ToolApprovalResponseContent.");
        }

        yield return new StreamingFunctionApprovalResponded
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            RequestId = approvalResponse.RequestId,
            Approved = approvalResponse.Approved,
            ItemId = idGenerator.GenerateMessageId()
        };
    }

    public override IEnumerable<StreamingResponseEvent> Complete() => [];
}
