// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Unit tests for AgentInvocationContext.
/// </summary>
public sealed class AgentInvocationContextTests
{
    [Fact]
    public void Constructor_WithIdGenerator_InitializesCorrectly()
    {
        // Arrange
        var idGenerator = new IdGenerator("resp_test123", "conv_test456");

        // Act
        var context = new AgentInvocationContext(idGenerator);

        // Assert
        Assert.NotNull(context);
        Assert.Same(idGenerator, context.IdGenerator);
        Assert.Equal("resp_test123", context.ResponseId);
        Assert.Equal("conv_test456", context.ConversationId);
        Assert.NotNull(context.JsonSerializerOptions);
    }

    [Fact]
    public void Constructor_WithoutJsonOptions_UsesDefaultOptions()
    {
        // Arrange
        var idGenerator = new IdGenerator("resp_test", "conv_test");

        // Act
        var context = new AgentInvocationContext(idGenerator);

        // Assert
        Assert.NotNull(context.JsonSerializerOptions);
        Assert.Same(OpenAIHostingJsonUtilities.DefaultOptions, context.JsonSerializerOptions);
    }

    [Fact]
    public void Constructor_WithCustomJsonOptions_UsesProvidedOptions()
    {
        // Arrange
        var idGenerator = new IdGenerator("resp_test", "conv_test");
        var customOptions = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };

        // Act
        var context = new AgentInvocationContext(idGenerator, customOptions);

        // Assert
        Assert.Same(customOptions, context.JsonSerializerOptions);
    }

    [Fact]
    public void ResponseId_ReturnsIdGeneratorResponseId()
    {
        // Arrange
        const string ResponseId = "resp_property_test";
        var idGenerator = new IdGenerator(ResponseId, "conv_test");
        var context = new AgentInvocationContext(idGenerator);

        // Act
        string result = context.ResponseId;

        // Assert
        Assert.Equal(ResponseId, result);
        Assert.Equal(idGenerator.ResponseId, result);
    }

    [Fact]
    public void ConversationId_ReturnsIdGeneratorConversationId()
    {
        // Arrange
        const string ConversationId = "conv_property_test";
        var idGenerator = new IdGenerator("resp_test", ConversationId);
        var context = new AgentInvocationContext(idGenerator);

        // Act
        string result = context.ConversationId;

        // Assert
        Assert.Equal(ConversationId, result);
        Assert.Equal(idGenerator.ConversationId, result);
    }
}
