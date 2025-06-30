// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

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
            OnIntermediateMessages = msg => Task.CompletedTask
        };

        // Act
        var clone = new AgentRunOptions(options);

        // Assert
        Assert.Equal(options.OnIntermediateMessages, clone.OnIntermediateMessages);
    }

    [Fact]
    public void CloningConstructorThrowsIfNull()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentRunOptions(null!));
    }
}
