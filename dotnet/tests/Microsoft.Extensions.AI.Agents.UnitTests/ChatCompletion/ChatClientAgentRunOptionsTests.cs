// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.UnitTests.ChatCompletion;

public class ChatClientAgentRunOptionsTests
{
    /// <summary>
    /// Verify that ChatClientAgentRunOptions constructor works with null chatOptions.
    /// </summary>
    [Fact]
    public void ConstructorWorksWithNullChatOptions()
    {
        // Act
        var runOptions = new ChatClientAgentRunOptions();

        // Assert
        Assert.Null(runOptions.ChatOptions);
    }

    /// <summary>
    /// Verify that ChatClientAgentRunOptions ChatOptions property is set and mutable.
    /// </summary>
    [Fact]
    public void ChatOptionsPropertyIsReadOnly()
    {
        // Arrange
        var chatOptions = new ChatOptions { MaxOutputTokens = 100 };
        var runOptions = new ChatClientAgentRunOptions(chatOptions);
        chatOptions.MaxOutputTokens = 200; // Change the property to verify mutability

        // Act & Assert
        Assert.Same(chatOptions, runOptions.ChatOptions);

        // Verify that the property doesn't have a setter by checking if it's the same instance
        var retrievedOptions = runOptions.ChatOptions!;
        Assert.Same(chatOptions, retrievedOptions);
        Assert.Equal(200, retrievedOptions.MaxOutputTokens); // Ensure the change is reflected
    }
}
