// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Streaming;

/// <summary>
/// A generator for streaming events from function approval request content.
/// This is a non-standard DevUI extension for human-in-the-loop scenarios.
/// </summary>
internal sealed class FunctionApprovalRequestEventGenerator(
        IdGenerator idGenerator,
        SequenceNumber seq,
        int outputIndex,
        JsonSerializerOptions jsonSerializerOptions) : StreamingEventGenerator
{
    public override bool IsSupported(AIContent content) => content is FunctionApprovalRequestContent;

    public override IEnumerable<StreamingResponseEvent> ProcessContent(AIContent content)
    {
        if (content is not FunctionApprovalRequestContent approvalRequest)
        {
            throw new InvalidOperationException("FunctionApprovalRequestEventGenerator only supports FunctionApprovalRequestContent.");
        }

        yield return new StreamingFunctionApprovalRequested
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            RequestId = approvalRequest.Id,
            ItemId = idGenerator.GenerateMessageId(),
            FunctionCall = new FunctionCallInfo
            {
                Id = approvalRequest.FunctionCall.CallId,
                Name = approvalRequest.FunctionCall.Name,
                Arguments = JsonSerializer.SerializeToElement(
                    approvalRequest.FunctionCall.Arguments,
                    jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object>)))
            }
        };
    }

    public override IEnumerable<StreamingResponseEvent> Complete() => [];
}
