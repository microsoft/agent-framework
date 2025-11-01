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
#pragma warning disable MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates.
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
#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
                Arguments = JsonSerializer.SerializeToElement(approvalRequest.FunctionCall.Arguments, jsonSerializerOptions)
#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
            }
        };
    }

    public override IEnumerable<StreamingResponseEvent> Complete() => [];
}
#pragma warning restore MEAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates.
