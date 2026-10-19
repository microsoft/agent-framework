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
internal sealed class ToolApprovalRequestEventGenerator(
        IdGenerator idGenerator,
        SequenceNumber seq,
        int outputIndex,
        JsonSerializerOptions jsonSerializerOptions) : StreamingEventGenerator
{
    public override bool IsSupported(AIContent content) => content is ToolApprovalRequestContent;

    public override IEnumerable<StreamingResponseEvent> ProcessContent(AIContent content)
    {
        if (content is not ToolApprovalRequestContent approvalRequest)
        {
            throw new InvalidOperationException("ToolApprovalRequestEventGenerator only supports ToolApprovalRequestContent.");
        }

        if (approvalRequest.ToolCall is not FunctionCallContent functionCall)
        {
            yield break;
        }
        yield return new StreamingFunctionApprovalRequested
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            RequestId = approvalRequest.RequestId,
            ItemId = idGenerator.GenerateMessageId(),
            FunctionCall = new FunctionCallInfo
            {
                Id = functionCall.CallId,
                Name = functionCall.Name,
                // DevUI requires an arguments object. Represent a no-argument call as an empty object
                // so its response can pass the same strict wire validation as calls with arguments.
                Arguments = JsonSerializer.SerializeToElement(
                    functionCall.Arguments ?? new Dictionary<string, object?>(),
                    jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object>)))
            }
        };
    }

    public override IEnumerable<StreamingResponseEvent> Complete() => [];
}
