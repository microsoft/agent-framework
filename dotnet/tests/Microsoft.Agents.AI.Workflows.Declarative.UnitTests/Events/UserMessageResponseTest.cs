// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Extensions.AI;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Verify <see cref="UserMessageResponse"/> class
/// </summary>
public sealed class UserMessageResponseTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerializationText()
    {
        // Arrange & Act
        UserMessageResponse copy = VerifyEventSerialization(new UserMessageResponse("test response"));

        // Assert
        Assert.Equal("test response", copy.Value.Text);
    }

    [Fact]
    public void VerifySerializationMessage()
    {
        // Arrange & Act
        UserMessageResponse copy = VerifyEventSerialization(new UserMessageResponse(new ChatMessage(ChatRole.User, "test response")));

        // Assert
        Assert.Equal("test response", copy.Value.Text);
    }
}
