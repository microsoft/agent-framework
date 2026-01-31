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
        AgentRequestMessageSource result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSource.External, result);
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
        AgentRequestMessageSource result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSource.External, result);
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
        AgentRequestMessageSource result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSource.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithExternalSource_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSource.AdditionalPropertiesKey, AgentRequestMessageSource.External }
            }
        };

        // Act
        AgentRequestMessageSource result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSource.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithAIContextProviderSource_ReturnsAIContextProvider()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSource.AdditionalPropertiesKey, AgentRequestMessageSource.AIContextProvider }
            }
        };

        // Act
        AgentRequestMessageSource result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSource.AIContextProvider, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithChatHistorySource_ReturnsChatHistory()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSource.AdditionalPropertiesKey, AgentRequestMessageSource.ChatHistory }
            }
        };

        // Act
        AgentRequestMessageSource result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSource.ChatHistory, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithCustomSource_ReturnsCustomSource()
    {
        // Arrange
        AgentRequestMessageSource customSource = new("CustomSource");
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSource.AdditionalPropertiesKey, customSource }
            }
        };

        // Act
        AgentRequestMessageSource result = message.GetAgentRequestMessageSource();

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
                { AgentRequestMessageSource.AdditionalPropertiesKey, "NotAnAgentRequestMessageSource" }
            }
        };

        // Act
        AgentRequestMessageSource result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSource.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSource_WithNullValue_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSource.AdditionalPropertiesKey, null! }
            }
        };

        // Act
        AgentRequestMessageSource result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSource.External, result);
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
                { AgentRequestMessageSource.AdditionalPropertiesKey, AgentRequestMessageSource.ChatHistory },
                { "AnotherProperty", 123 }
            }
        };

        // Act
        AgentRequestMessageSource result = message.GetAgentRequestMessageSource();

        // Assert
        Assert.Equal(AgentRequestMessageSource.ChatHistory, result);
    }

    #endregion
}
