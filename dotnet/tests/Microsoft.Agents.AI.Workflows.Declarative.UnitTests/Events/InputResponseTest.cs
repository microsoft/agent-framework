// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Base class for event tests.
/// </summary>
public sealed class InputResponseTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerializationText()
    {
        InputResponse copy = VerifyEventSerialization(new InputResponse("test response"));
        Assert.Equal("test response", copy.Value.Text);
    }

    [Fact]
    public void VerifySerializationMessage()
    {
        InputResponse copy = VerifyEventSerialization(new InputResponse(new ChatMessage(ChatRole.User, "test response")));
        Assert.Equal("test response", copy.Value.Text);
    }
}
