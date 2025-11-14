// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Events;

/// <summary>
/// Verify <see cref="AnswerRequest"/> class
/// </summary>
public sealed class UserMessageRequestTest(ITestOutputHelper output) : EventTest(output)
{
    [Fact]
    public void VerifySerialization()
    {
        // Arrange & Act
        AnswerRequest copy = VerifyEventSerialization(new AnswerRequest("wassup"));

        // Assert
        Assert.Equal("wassup", copy.Prompt);
    }
}
