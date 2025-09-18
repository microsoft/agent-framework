// Copyright (c) Microsoft. All rights reserved.

using System;

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
        var options = new AgentRunOptions();

        // Act
        var clone = new AgentRunOptions(options);
        Assert.NotNull(clone);
    }

    [Fact]
    public void CloningConstructorThrowsIfNull() =>
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentRunOptions(null!));
}
