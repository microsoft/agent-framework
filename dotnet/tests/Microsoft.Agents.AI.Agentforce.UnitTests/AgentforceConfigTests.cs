// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Agentforce;

namespace Microsoft.Agents.AI.Agentforce.UnitTests;

public class AgentforceConfigTests
{
    [Fact]
    public void Constructor_WithValidParameters_SetsProperties()
    {
        // Arrange
        const string myDomainHost = "test-org.my.salesforce.com";
        const string consumerKey = "test-consumer-key";
        const string consumerSecret = "test-consumer-secret";
        const string agentId = "test-agent-id";

        // Act
        var config = new AgentforceConfig(myDomainHost, consumerKey, consumerSecret, agentId);

        // Assert
        Assert.Equal(myDomainHost, config.MyDomainHost);
        Assert.Equal(consumerKey, config.ConsumerKey);
        Assert.Equal(consumerSecret, config.ConsumerSecret);
        Assert.Equal(agentId, config.AgentId);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Constructor_WithNullOrEmptyMyDomainHost_Throws(string? myDomainHost)
    {
        // Act & Assert
        Assert.ThrowsAny<ArgumentException>(() =>
            new AgentforceConfig(myDomainHost!, "key", "secret", "agent-id"));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Constructor_WithNullOrEmptyConsumerKey_Throws(string? consumerKey)
    {
        // Act & Assert
        Assert.ThrowsAny<ArgumentException>(() =>
            new AgentforceConfig("domain.com", consumerKey!, "secret", "agent-id"));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Constructor_WithNullOrEmptyConsumerSecret_Throws(string? consumerSecret)
    {
        // Act & Assert
        Assert.ThrowsAny<ArgumentException>(() =>
            new AgentforceConfig("domain.com", "key", consumerSecret!, "agent-id"));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void Constructor_WithNullOrEmptyAgentId_Throws(string? agentId)
    {
        // Act & Assert
        Assert.ThrowsAny<ArgumentException>(() =>
            new AgentforceConfig("domain.com", "key", "secret", agentId!));
    }
}
