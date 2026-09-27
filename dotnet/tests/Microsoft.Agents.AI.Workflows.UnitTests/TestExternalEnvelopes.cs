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

    object IExternalRequestEnvelope.CreateResponse(IList<ChatMessage> messages) => messages;
}
