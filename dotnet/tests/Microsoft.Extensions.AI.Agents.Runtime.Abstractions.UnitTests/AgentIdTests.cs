// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Extensions.AI.Agents.Runtime.Abstractions.Tests;

public class AgentIdTests()
{
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("invalid\u007Fkey")] // DEL character (127) is outside ASCII 32-126 range
    [InlineData("invalid\u0000key")] // NULL character is outside ASCII 32-126 range
    [InlineData("invalid\u0010key")] // Control character is outside ASCII 32-126 range
    [InlineData("InvalidKey💀")] // Control character is outside ASCII 32-126 range
    public void AgentIdShouldThrowArgumentExceptionWithInvalidKey(string? invalidKey)
    {
        // Act & Assert
        ArgumentException exception = Assert.Throws<ArgumentException>(() => new ActorId("validType", invalidKey!));
        Assert.Contains("Invalid ActorId key", exception.Message);
    }

    [Fact]
    public void AgentIdShouldInitializeCorrectlyTest()
    {
        ActorId agentId = new("TestType", "TestKey");

        Assert.Equal("TestType", agentId.Type.Name);
        Assert.Equal("TestKey", agentId.Key);
    }

    [Fact]
    public void AgentIdShouldParseFromStringTest()
    {
        ActorId agentId = ActorId.Parse("ParsedType/ParsedKey");

        Assert.Equal("ParsedType", agentId.Type.Name);
        Assert.Equal("ParsedKey", agentId.Key);
    }

    [Fact]
    public void AgentIdShouldCompareEqualityCorrectlyTest()
    {
        ActorId agentId1 = new("SameType", "SameKey");
        ActorId agentId2 = new("SameType", "SameKey");
        ActorId agentId3 = new("DifferentType", "DifferentKey");

        Assert.Equal(agentId2, agentId1);
        Assert.NotEqual(agentId3, agentId1);
        Assert.True(agentId1 == agentId2);
        Assert.True(agentId1 != agentId3);
    }

    [Fact]
    public void AgentIdShouldGenerateCorrectHashCodeTest()
    {
        ActorId agentId1 = new("HashType", "HashKey");
        ActorId agentId2 = new("HashType", "HashKey");
        ActorId agentId3 = new("DifferentType", "DifferentKey");

        Assert.Equal(agentId2.GetHashCode(), agentId1.GetHashCode());
        Assert.NotEqual(agentId3.GetHashCode(), agentId1.GetHashCode());
    }

    [Fact]
    public void AgentIdShouldReturnCorrectToStringTest()
    {
        ActorId agentId = new("ToStringType", "ToStringKey");

        Assert.Equal("ToStringType/ToStringKey", agentId.ToString());
    }

    [Fact]
    public void AgentIdShouldCompareInequalityForWrongTypeTest()
    {
        ActorId agentId1 = new("Type1", "Key1");

        Assert.False(agentId1.Equals(Guid.NewGuid()));
    }

    [Fact]
    public void AgentIdShouldCompareInequalityCorrectlyTest()
    {
        ActorId agentId1 = new("Type1", "Key1");
        ActorId agentId2 = new("Type2", "Key2");

        Assert.True(agentId1 != agentId2);
    }
}
