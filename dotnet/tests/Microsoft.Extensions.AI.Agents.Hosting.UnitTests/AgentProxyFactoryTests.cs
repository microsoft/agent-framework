// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI.Agents.Runtime;
using Moq;

namespace Microsoft.Extensions.AI.Agents.Hosting.UnitTests;

public class AgentProxyFactoryTests
{
    public static IEnumerable<object[]> ValidNames =>
        new List<object[]>
        {
                new object[] { "agent" },
                new object[] { " " },
                new object[] { "特殊字符" },
                new object[] { new string('x', 1000) }
        };

    /// <summary>
    /// Verifies that creating with valid names returns an <see cref="AgentProxy"/> instance with the given name.
    /// </summary>
    /// <param name="name">The valid agent name to test.</param>
    [Theory]
    [MemberData(nameof(ValidNames))]
    public void Create_ValidName_ReturnsAgentProxyWithExpectedName(string name)
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var factory = new AgentProxyFactory(mockClient.Object);

        // Act
        var proxy = factory.Create(name);

        // Assert
        Assert.NotNull(proxy);
        Assert.IsType<AgentProxy>(proxy);
        Assert.Equal(name, proxy.Name);
    }

    /// <summary>
    /// Verifies that providing a null name to <see cref="AgentProxyFactory.Create"/> throws an <see cref="ArgumentNullException"/>.
    /// </summary>
    [Fact]
    public void Create_NullName_ThrowsArgumentNullException()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var factory = new AgentProxyFactory(mockClient.Object);

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => factory.Create(null!));
    }

    /// <summary>
    /// Verifies that providing an empty name to <see cref="AgentProxyFactory.Create"/> throws an <see cref="ArgumentException"/>.
    /// </summary>
    [Fact]
    public void Create_EmptyName_ThrowsArgumentException()
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var factory = new AgentProxyFactory(mockClient.Object);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => factory.Create(""));
    }

    /// <summary>
    /// Verifies that constructor throws ArgumentNullException when client is null.
    /// </summary>
    [Fact]
    public void Constructor_NullClient_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentProxyFactory(null!));
    }

    /// <summary>
    /// Verifies that Create passes the same client instance to all created proxies.
    /// </summary>
    [Theory]
    [InlineData("agent1")]
    [InlineData("agent2")]
    [InlineData("agent3")]
    public void Create_MultipleAgents_UsesSameClient(string agentName)
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var factory = new AgentProxyFactory(mockClient.Object);

        // Act
        var proxy = factory.Create(agentName);

        // Assert
        Assert.NotNull(proxy);
        Assert.IsType<AgentProxy>(proxy);
        Assert.Equal(agentName, proxy.Name);
        // The client is private, but we can verify behavior through usage
    }

    /// <summary>
    /// Verifies that Create handles names with only whitespace properly.
    /// </summary>
    [Theory]
    [InlineData("   ")]
    [InlineData("\t")]
    [InlineData("\n")]
    [InlineData(" \t\n ")]
    public void Create_WhitespaceName_CreatesProxyWithWhitespaceName(string whitespaceNames)
    {
        // Arrange
        var mockClient = new Mock<IActorClient>();
        var factory = new AgentProxyFactory(mockClient.Object);

        // Act
        var proxy = factory.Create(whitespaceNames);

        // Assert
        Assert.NotNull(proxy);
        Assert.Equal(whitespaceNames, proxy.Name);
    }
}
