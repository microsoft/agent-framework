// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;

namespace Microsoft.Agents.Abstractions.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AgentRunOptions"/> class.
/// </summary>
public class AgentRunOptionsTests
{
    [Fact]
    public void CloningConstructorCopiesProperties()
    {
        // Arrange
        var options = new AgentRunOptions
        {
            AdditionalInstructions = "Test instructions",
            OnIntermediateMessage = msg => Task.CompletedTask
        };

        // Act
        var clone = new AgentRunOptions(options);

        // Assert
        Assert.Equal(options.AdditionalInstructions, clone.AdditionalInstructions);
        Assert.Equal(options.OnIntermediateMessage, clone.OnIntermediateMessage);
    }

    [Fact]
    public void CloningConstructorThrowsIfNull()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentRunOptions(null!));
    }
}
