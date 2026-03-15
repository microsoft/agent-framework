// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Streaming;

/// <summary>
/// A generator for streaming events from tool approval request content.
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

        var toolCallInfo = approvalRequest.ToolCall switch
        {
            FunctionCallContent fcc => (ToolCallInfo)new FunctionToolCallInfo
            {
                Id = fcc.CallId,
                Name = fcc.Name,
                Arguments = fcc.Arguments is not null
                    ? JsonSerializer.SerializeToElement(
                        fcc.Arguments,
                        jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object>)))
                    : default
            },
            McpServerToolCallContent mcc => new McpToolCallInfo
            {
                Id = mcc.CallId,
                Name = mcc.Name,
                ServerName = mcc.ServerName ?? string.Empty,
                Arguments = mcc.Arguments is not null
                    ? JsonSerializer.SerializeToElement(
                        mcc.Arguments,
                        jsonSerializerOptions.GetTypeInfo(typeof(IDictionary<string, object>)))
                    : default
            },
            _ => new FunctionToolCallInfo
            {
                Id = approvalRequest.ToolCall.CallId,
                Name = approvalRequest.ToolCall.CallId,
                Arguments = default
            }
        };

        yield return new StreamingToolApprovalRequested
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            RequestId = approvalRequest.RequestId,
            ItemId = idGenerator.GenerateMessageId(),
            ToolCall = toolCallInfo
        };
    }

    public override IEnumerable<StreamingResponseEvent> Complete() => [];
}
