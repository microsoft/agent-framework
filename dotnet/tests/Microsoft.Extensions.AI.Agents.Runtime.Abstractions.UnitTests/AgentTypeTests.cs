// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI.Agents.Runtime.Abstractions.Tests;

public class AgentTypeTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("invalid type")] // Agent type must only contain alphanumeric letters or underscores
    [InlineData("123invalidType")] // Agent type cannot start with a number
    [InlineData("invalid@type")] // Agent type must only contain alphanumeric letters or underscores
    [InlineData("invalid-type")] // Agent type cannot alphanumeric underscores.
    public void AgentIdShouldThrowArgumentExceptionWithInvalidType(string? invalidType)
    {
        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() => new ActorType(invalidType!));
        Assert.Contains("Invalid type", exception.Message);
    }

    [Fact]
    public void ConversionToStringTest()
    {
        // Arrange
        ActorType agentType = new("TestAgent");

        // Assert
        Assert.Equal("TestAgent", agentType.Name);
        Assert.Equal("TestAgent", agentType.ToString());
    }
}
