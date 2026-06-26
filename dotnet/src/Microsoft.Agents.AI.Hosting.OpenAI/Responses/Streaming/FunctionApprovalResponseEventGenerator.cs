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
internal sealed class FunctionApprovalResponseEventGenerator(
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

        var itemId = idGenerator.GenerateMessageId();

        // Build ItemResource for MCP approval responses (spec-aligned storage).
        // Local function approval responses have no corresponding OpenAI item type,
        // so only MCP approvals are stored.
        ItemResource? item = approvalResponse.ToolCall switch
        {
            McpServerToolCallContent => new MCPApprovalResponseItemResource
            {
                Id = itemId,
                ApprovalRequestId = approvalResponse.RequestId,
                Approve = approvalResponse.Approved,
            },
            _ => null
        };

        if (item is not null)
        {
            yield return new StreamingOutputItemAdded
            {
                SequenceNumber = seq.Increment(),
                OutputIndex = outputIndex,
                Item = item
            };
        }

        // Emit the custom DevUI event for the frontend
        yield return new StreamingFunctionApprovalResponded
        {
            SequenceNumber = seq.Increment(),
            OutputIndex = outputIndex,
            RequestId = approvalResponse.RequestId,
            Approved = approvalResponse.Approved,
            ItemId = itemId
        };

        if (item is not null)
        {
            yield return new StreamingOutputItemDone
            {
                SequenceNumber = seq.Increment(),
                OutputIndex = outputIndex,
                Item = item
            };
        }
    }

    public override IEnumerable<StreamingResponseEvent> Complete() => [];
}
