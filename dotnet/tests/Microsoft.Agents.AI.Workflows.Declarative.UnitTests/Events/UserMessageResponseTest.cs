// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Verify <see cref="AnswerResponse"/> class
/// </summary>
public sealed class UserMessageResponseTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerializationText()
    {
        // Arrange & Act
        AnswerResponse copy = VerifyEventSerialization(new AnswerResponse("test response"));

        // Assert
        Assert.Equal("test response", copy.Value.Text);
    }

    [Fact]
    public void VerifySerializationMessage()
    {
        // Arrange & Act
        AnswerResponse copy = VerifyEventSerialization(new AnswerResponse(new ChatMessage(ChatRole.User, "test response")));

        // Assert
        Assert.Equal("test response", copy.Value.Text);
    }
}
