// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal sealed class TestExternalRequestEnvelope : IExternalRequestEnvelope
{
    [JsonConstructor]
    public TestExternalRequestEnvelope(FunctionCallContent functionCall)
    {
        this.FunctionCall = functionCall;
    }

    public FunctionCallContent FunctionCall { get; }

    AIContent? IExternalRequestEnvelope.GetInnerRequestContent() => this.FunctionCall;

    object IExternalRequestEnvelope.CreateResponse(IList<ChatMessage> messages) => new TestExternalResponseEnvelope(messages, requestId: null);
}

internal sealed class TestExternalResponseEnvelope : IExternalResponseEnvelope
{
    [JsonConstructor]
    public TestExternalResponseEnvelope(IList<ChatMessage> messages, string? requestId)
    {
        this.Messages = messages;
        this.RequestId = requestId;
    }

    public IList<ChatMessage> Messages { get; }

    public string? RequestId { get; }

    object IExternalResponseEnvelope.WithRequestId(string requestId) => new TestExternalResponseEnvelope(this.Messages, requestId);
}
