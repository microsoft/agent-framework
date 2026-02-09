// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="ChatMessageExtensions"/> class.
/// </summary>
public sealed class ChatMessageExtensionsTests
{
    #region GetAgentRequestMessageSource Tests

    [Fact]
    public void GetAgentRequestMessageSource_WithNoAdditionalProperties_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello");

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithNullAdditionalProperties_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = null
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithEmptyAdditionalProperties_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary()
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithExternalSource_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceType.AdditionalPropertiesKey, AgentRequestMessageSourceType.External }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithAIContextProviderSource_ReturnsAIContextProvider()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceType.AdditionalPropertiesKey, AgentRequestMessageSourceType.AIContextProvider }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithChatHistorySource_ReturnsChatHistory()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceType.AdditionalPropertiesKey, AgentRequestMessageSourceType.ChatHistory }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithCustomSource_ReturnsCustomSource()
    {
        // Arrange
        AgentRequestMessageSourceType customSource = new("CustomSource");
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceType.AdditionalPropertiesKey, customSource }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(customSource, result);
        Assert.Equal("CustomSource", result.Value);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithWrongKeyType_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceType.AdditionalPropertiesKey, "NotAnAgentRequestMessageSource" }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithNullValue_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceType.AdditionalPropertiesKey, null! }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithMultipleProperties_ReturnsCorrectSource()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { "OtherProperty", "SomeValue" },
                { AgentRequestMessageSourceType.AdditionalPropertiesKey, AgentRequestMessageSourceType.ChatHistory },
                { "AnotherProperty", 123 }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, result);
    }

    #endregion
}
