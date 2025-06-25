// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Orchestration.GroupChat;

namespace Microsoft.Agents.Orchestration.UnitTest;

public class ChatGroupExtensionsTests
{
    [Fact]
    public void FormatNamesWithMultipleAgentsReturnsCommaSeparatedList()
    {
        // Arrange
        GroupChatTeam group = new()
        {
            { "AgentOne", ("agent1", "First agent description") },
            { "AgentTwo", ("agent2", "Second agent description") },
            { "AgentThree", ("agent3", "Third agent description") }
        };

        // Act
        string result = group.FormatNames();

        // Assert
        Assert.Equal("AgentOne,AgentTwo,AgentThree", result);
    }

    [Fact]
    public void FormatNamesWithSingleAgentReturnsSingleName()
    {
        // Arrange
        GroupChatTeam group = new()
        {
            { "AgentOne", ("agent1", "First agent description") },
        };

        // Act
        string result = group.FormatNames();

        // Assert
        Assert.Equal("AgentOne", result);
    }

    [Fact]
    public void FormatNamesWithEmptyGroupReturnsEmptyString()
    {
        // Arrange
        GroupChatTeam group = [];

        // Act
        string result = group.FormatNames();

        // Assert
        Assert.Equal(string.Empty, result);
    }

    [Fact]
    public void FormatListWithMultipleAgentsReturnsMarkdownList()
    {
        // Arrange
        GroupChatTeam group = new()
        {
            { "AgentOne", ("agent1", "First agent description") },
            { "AgentTwo", ("agent2", "Second agent description") },
            { "AgentThree", ("agent3", "Third agent description") }
        };

        // Act
        string result = group.FormatList();

        // Assert
        const string Expected =
            """
            - AgentOne: First agent description
            - AgentTwo: Second agent description
            - AgentThree: Third agent description
            """;
        Assert.Equal(Expected, result);
    }

    [Fact]
    public void FormatListWithEmptyGroupReturnsEmptyString()
    {
        // Arrange
        GroupChatTeam group = [];

        // Act & Assert
        Assert.Equal(string.Empty, group.FormatNames());
        Assert.Equal(string.Empty, group.FormatList());
    }
}
