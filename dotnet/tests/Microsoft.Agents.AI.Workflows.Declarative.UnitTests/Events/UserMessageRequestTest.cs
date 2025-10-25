// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Verify <see cref="UserMessageRequest"/> class
/// </summary>
public sealed class UserMessageRequestTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerialization()
    {
        // Arrange & Act
        UserMessageRequest copy = VerifyEventSerialization(new UserMessageRequest("wassup"));

        // Assert
        Assert.Equal("wassup", copy.Prompt);
    }
}
