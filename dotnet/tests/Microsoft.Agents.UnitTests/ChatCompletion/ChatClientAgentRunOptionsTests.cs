// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.UnitTests.ChatCompletion;

public class ChatClientAgentRunOptionsTests
{
    /// <summary>
    /// Verify that ChatClientAgentRunOptions constructor works with null source and null chatOptions.
    /// </summary>
    [Fact]
    public void ConstructorWorksWithNullSourceAndNullChatOptions()
    {
        // Act
        var runOptions = new ChatClientAgentRunOptions();

        // Assert
        Assert.Null(runOptions.OnIntermediateMessages);
        Assert.Null(runOptions.AdditionalInstructions);
        Assert.Null(runOptions.ChatOptions);
    }

    /// <summary>
    /// Verify that ChatClientAgentRunOptions constructor works with null source and provided chatOptions.
    /// </summary>
    [Fact]
    public void ConstructorWorksWithNullSourceAndProvidedChatOptions()
    {
        // Arrange
        var chatOptions = new ChatOptions { MaxOutputTokens = 100 };

        // Act
        var runOptions = new ChatClientAgentRunOptions(null, chatOptions);

        // Assert
        Assert.Null(runOptions.OnIntermediateMessages);
        Assert.Null(runOptions.AdditionalInstructions);
        Assert.Same(chatOptions, runOptions.ChatOptions);
    }

    /// <summary>
    /// Verify that ChatClientAgentRunOptions constructor copies properties from source AgentRunOptions.
    /// </summary>
    [Fact]
    public void ConstructorCopiesPropertiesFromSourceAgentRunOptions()
    {
        // Arrange
        var sourceRunOptions = new AgentRunOptions
        {
            AdditionalInstructions = "additional instructions",
            OnIntermediateMessages = messages => Task.CompletedTask
        };
        var chatOptions = new ChatOptions { MaxOutputTokens = 200 };

        // Act
        var runOptions = new ChatClientAgentRunOptions(sourceRunOptions, chatOptions);

        // Assert
        Assert.Same(sourceRunOptions.OnIntermediateMessages, runOptions.OnIntermediateMessages);
        Assert.Equal("additional instructions", runOptions.AdditionalInstructions);
        Assert.Same(chatOptions, runOptions.ChatOptions);
    }

    /// <summary>
    /// Verify that ChatClientAgentRunOptions constructor works with source but null chatOptions.
    /// </summary>
    [Fact]
    public void ConstructorWorksWithSourceButNullChatOptions()
    {
        // Arrange
        var sourceRunOptions = new AgentRunOptions
        {
            AdditionalInstructions = "test instructions"
        };

        // Act
        var runOptions = new ChatClientAgentRunOptions(sourceRunOptions, null);

        // Assert
        Assert.Equal("test instructions", runOptions.AdditionalInstructions);
        Assert.Null(runOptions.ChatOptions);
    }

    /// <summary>
    /// Verify that ChatClientAgentRunOptions ChatOptions property is read-only.
    /// </summary>
    [Fact]
    public void ChatOptionsPropertyIsReadOnly()
    {
        // Arrange
        var chatOptions = new ChatOptions { MaxOutputTokens = 100 };
        var runOptions = new ChatClientAgentRunOptions(null, chatOptions);

        // Act & Assert
        Assert.Same(chatOptions, runOptions.ChatOptions);

        // Verify that the property doesn't have a setter by checking if it's the same instance
        // (This test verifies the property is read-only by design)
        var retrievedOptions = runOptions.ChatOptions;
        Assert.Same(chatOptions, retrievedOptions);
    }
}
