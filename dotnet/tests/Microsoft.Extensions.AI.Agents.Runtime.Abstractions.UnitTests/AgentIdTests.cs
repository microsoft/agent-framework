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
        ArgumentException exception = Assert.Throws<ArgumentException>(() => new AgentId("validType", invalidKey!));
        Assert.Contains("Invalid AgentId key", exception.Message);
    }

    [Fact]
    public void AgentIdShouldInitializeCorrectlyTest()
    {
        AgentId agentId = new("TestType", "TestKey");

        Assert.Equal("TestType", agentId.Type);
        Assert.Equal("TestKey", agentId.Key);
    }

    [Fact]
    public void AgentIdShouldConvertFromTupleTest()
    {
        (string, string) agentTuple = ("TupleType", "TupleKey");
        AgentId agentId = new(agentTuple);

        Assert.Equal("TupleType", agentId.Type);
        Assert.Equal("TupleKey", agentId.Key);
    }

    [Fact]
    public void AgentIdShouldConvertFromAgentType()
    {
        AgentType agentType = "TestType";
        AgentId agentId = new(agentType, "TestKey");

        Assert.Equal("TestType", agentId.Type);
        Assert.Equal("TestKey", agentId.Key);
    }

    [Fact]
    public void AgentIdShouldParseFromStringTest()
    {
        AgentId agentId = AgentId.FromStr("ParsedType/ParsedKey");

        Assert.Equal("ParsedType", agentId.Type);
        Assert.Equal("ParsedKey", agentId.Key);
    }

    [Fact]
    public void AgentIdShouldCompareEqualityCorrectlyTest()
    {
        AgentId agentId1 = new("SameType", "SameKey");
        AgentId agentId2 = new("SameType", "SameKey");
        AgentId agentId3 = new("DifferentType", "DifferentKey");

        Assert.Equal(agentId2, agentId1);
        Assert.NotEqual(agentId3, agentId1);
        Assert.True(agentId1 == agentId2);
        Assert.True(agentId1 != agentId3);
    }

    [Fact]
    public void AgentIdShouldGenerateCorrectHashCodeTest()
    {
        AgentId agentId1 = new("HashType", "HashKey");
        AgentId agentId2 = new("HashType", "HashKey");
        AgentId agentId3 = new("DifferentType", "DifferentKey");

        Assert.Equal(agentId2.GetHashCode(), agentId1.GetHashCode());
        Assert.NotEqual(agentId3.GetHashCode(), agentId1.GetHashCode());
    }

    [Fact]
    public void AgentIdShouldConvertExplicitlyFromStringTest()
    {
        AgentId agentId = (AgentId)"ConvertedType/ConvertedKey";

        Assert.Equal("ConvertedType", agentId.Type);
        Assert.Equal("ConvertedKey", agentId.Key);
    }

    [Fact]
    public void AgentIdShouldReturnCorrectToStringTest()
    {
        AgentId agentId = new("ToStringType", "ToStringKey");

        Assert.Equal("ToStringType/ToStringKey", agentId.ToString());
    }

    [Fact]
    public void AgentIdShouldCompareInequalityForWrongTypeTest()
    {
        AgentId agentId1 = new("Type1", "Key1");

        Assert.False(agentId1.Equals(Guid.NewGuid()));
    }

    [Fact]
    public void AgentIdShouldCompareInequalityCorrectlyTest()
    {
        AgentId agentId1 = new("Type1", "Key1");
        AgentId agentId2 = new("Type2", "Key2");

        Assert.True(agentId1 != agentId2);
    }
}
