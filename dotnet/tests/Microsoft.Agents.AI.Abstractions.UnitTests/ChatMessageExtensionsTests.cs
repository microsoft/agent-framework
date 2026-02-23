// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Contains tests for the <see cref="ChatMessageExtensions"/> class.
/// </summary>
public sealed class ChatMessageExtensionsTests
{
    #region GetAgentRequestMessageSourceType Tests

    [Fact]
    public void GetAgentRequestMessageSourceType_WithNoAdditionalProperties_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello");

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSourceType();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceType_WithNullAdditionalProperties_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = null
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSourceType();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceType_WithEmptyAdditionalProperties_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary()
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSourceType();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceType_WithExternalSourceType_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.External, "TestSourceId") }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSourceType();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceType_WithAIContextProviderSourceType_ReturnsAIContextProvider()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.AIContextProvider, "TestSourceId") }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSourceType();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceType_WithChatHistorySourceType_ReturnsChatHistory()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "TestSourceId") }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSourceType();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceType_WithCustomSourceType_ReturnsCustomSourceType()
    {
        // Arrange
        AgentRequestMessageSourceType customSourceType = new("CustomSourceType");
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(customSourceType, "TestSourceId") }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSourceType();

        // Assert
        Assert.Equal(customSourceType, result);
        Assert.Equal("CustomSourceType", result.Value);
    }

    [Fact]
    public void GetAgentRequestMessageSourceType_WithWrongAttributionType_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, "NotAnAgentRequestMessageSourceAttribution" }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSourceType();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceType_WithNullAttributionValue_ReturnsExternal()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, null! }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSourceType();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.External, result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceType_WithMultipleProperties_ReturnsCorrectSourceType()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { "OtherProperty", "SomeValue" },
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "TestSourceId") },
                { "AnotherProperty", 123 }
            }
        };

        // Act
        AgentRequestMessageSourceType result = message.GetAgentRequestMessageSourceType();

        // Assert
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, result);
    }

    #endregion

    #region GetAgentRequestMessageSourceId Tests

    [Fact]
    public void GetAgentRequestMessageSourceId_WithNoAdditionalProperties_ReturnsNull()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello");

        // Act
        string? result = message.GetAgentRequestMessageSourceId();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceId_WithNullAdditionalProperties_ReturnsNull()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = null
        };

        // Act
        string? result = message.GetAgentRequestMessageSourceId();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceId_WithEmptyAdditionalProperties_ReturnsNull()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary()
        };

        // Act
        string? result = message.GetAgentRequestMessageSourceId();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceId_WithAttribution_ReturnsSourceId()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.AIContextProvider, "MyProvider.FullName") }
            }
        };

        // Act
        string? result = message.GetAgentRequestMessageSourceId();

        // Assert
        Assert.Equal("MyProvider.FullName", result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceId_WithDifferentSourceIds_ReturnsCorrectSourceId()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "CustomHistorySourceId") }
            }
        };

        // Act
        string? result = message.GetAgentRequestMessageSourceId();

        // Assert
        Assert.Equal("CustomHistorySourceId", result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceId_WithWrongAttributionType_ReturnsNull()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, "NotAnAgentRequestMessageSourceAttribution" }
            }
        };

        // Act
        string? result = message.GetAgentRequestMessageSourceId();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceId_WithNullAttributionValue_ReturnsNull()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, null! }
            }
        };

        // Act
        string? result = message.GetAgentRequestMessageSourceId();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void GetAgentRequestMessageSourceId_WithMultipleProperties_ReturnsCorrectSourceId()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { "OtherProperty", "SomeValue" },
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.External, "ExpectedSourceId") },
                { "AnotherProperty", 123 }
            }
        };

        // Act
        string? result = message.GetAgentRequestMessageSourceId();

        // Assert
        Assert.Equal("ExpectedSourceId", result);
    }

    #endregion

    #region AsAgentRequestMessageSourcedMessage Tests

    [Fact]
    public void AsAgentRequestMessageSourcedMessage_WithNoAdditionalProperties_ReturnsClonesMessageWithAttribution()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello");

        // Act
        ChatMessage result = message.WithAgentRequestMessageSource(AgentRequestMessageSourceType.External, "TestSourceId");

        // Assert
        Assert.NotSame(message, result);
        Assert.Equal(AgentRequestMessageSourceType.External, result.GetAgentRequestMessageSourceType());
        Assert.Equal("TestSourceId", result.GetAgentRequestMessageSourceId());
    }

    [Fact]
    public void AsAgentRequestMessageSourcedMessage_WithNullAdditionalProperties_ReturnsClonesMessageWithAttribution()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = null
        };

        // Act
        ChatMessage result = message.WithAgentRequestMessageSource(AgentRequestMessageSourceType.AIContextProvider, "ProviderSourceId");

        // Assert
        Assert.NotSame(message, result);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, result.GetAgentRequestMessageSourceType());
        Assert.Equal("ProviderSourceId", result.GetAgentRequestMessageSourceId());
    }

    [Fact]
    public void AsAgentRequestMessageSourcedMessage_WithMatchingSourceTypeAndSourceId_ReturnsSameInstance()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.ChatHistory, "HistoryId") }
            }
        };

        // Act
        ChatMessage result = message.WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "HistoryId");

        // Assert
        Assert.Same(message, result);
    }

    [Fact]
    public void AsAgentRequestMessageSourcedMessage_WithDifferentSourceType_ReturnsClonesMessageWithNewAttribution()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.External, "SourceId") }
            }
        };

        // Act
        ChatMessage result = message.WithAgentRequestMessageSource(AgentRequestMessageSourceType.AIContextProvider, "SourceId");

        // Assert
        Assert.NotSame(message, result);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, result.GetAgentRequestMessageSourceType());
        Assert.Equal("SourceId", result.GetAgentRequestMessageSourceId());
    }

    [Fact]
    public void AsAgentRequestMessageSourcedMessage_WithDifferentSourceId_ReturnsClonesMessageWithNewAttribution()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.External, "OriginalId") }
            }
        };

        // Act
        ChatMessage result = message.WithAgentRequestMessageSource(AgentRequestMessageSourceType.External, "NewId");

        // Assert
        Assert.NotSame(message, result);
        Assert.Equal(AgentRequestMessageSourceType.External, result.GetAgentRequestMessageSourceType());
        Assert.Equal("NewId", result.GetAgentRequestMessageSourceId());
    }

    [Fact]
    public void AsAgentRequestMessageSourcedMessage_WithDefaultNullSourceId_ReturnsClonesMessageWithNullSourceId()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello");

        // Act
        ChatMessage result = message.WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory);

        // Assert
        Assert.NotSame(message, result);
        Assert.Equal(AgentRequestMessageSourceType.ChatHistory, result.GetAgentRequestMessageSourceType());
        Assert.Null(result.GetAgentRequestMessageSourceId());
    }

    [Fact]
    public void AsAgentRequestMessageSourcedMessage_WithMatchingSourceTypeAndNullSourceId_ReturnsSameInstance()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, new AgentRequestMessageSourceAttribution(AgentRequestMessageSourceType.External, null) }
            }
        };

        // Act
        ChatMessage result = message.WithAgentRequestMessageSource(AgentRequestMessageSourceType.External);

        // Assert
        Assert.Same(message, result);
    }

    [Fact]
    public void AsAgentRequestMessageSourcedMessage_DoesNotModifyOriginalMessage()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello");

        // Act
        ChatMessage result = message.WithAgentRequestMessageSource(AgentRequestMessageSourceType.AIContextProvider, "ProviderId");

        // Assert
        Assert.Null(message.AdditionalProperties);
        Assert.NotNull(result.AdditionalProperties);
        Assert.Equal(AgentRequestMessageSourceType.AIContextProvider, result.GetAgentRequestMessageSourceType());
    }

    [Fact]
    public void AsAgentRequestMessageSourcedMessage_WithWrongAttributionType_ReturnsClonesMessageWithNewAttribution()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                { AgentRequestMessageSourceAttribution.AdditionalPropertiesKey, "NotAnAttribution" }
            }
        };

        // Act
        ChatMessage result = message.WithAgentRequestMessageSource(AgentRequestMessageSourceType.External, "SourceId");

        // Assert
        Assert.NotSame(message, result);
        Assert.Equal(AgentRequestMessageSourceType.External, result.GetAgentRequestMessageSourceType());
        Assert.Equal("SourceId", result.GetAgentRequestMessageSourceId());
    }

    [Fact]
    public void AsAgentRequestMessageSourcedMessage_PreservesMessageContent()
    {
        // Arrange
        ChatMessage message = new(ChatRole.Assistant, "Test content");

        // Act
        ChatMessage result = message.WithAgentRequestMessageSource(AgentRequestMessageSourceType.ChatHistory, "HistoryId");

        // Assert
        Assert.Equal(ChatRole.Assistant, result.Role);
        Assert.Equal("Test content", result.Text);
    }

    #endregion
}
