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
        Assert.NotNull(runOptions.ChatOptions);
    }

    /// <summary>
    /// Verify that ChatClientAgentRunOptions ChatOptions property is set and mutable.
    /// </summary>
    [Fact]
    public void ChatOptionsPropertyIsCloned()
    {
        // Arrange
        var chatOptions = new ChatOptions { MaxOutputTokens = 100 };
        var runOptions = new ChatClientAgentRunOptions(null, chatOptions);
        chatOptions.MaxOutputTokens = 200; // Change the property to verify mutability

        // Act & Assert
        Assert.NotSame(chatOptions, runOptions.ChatOptions);

        // Verify that the property doesn't have a setter by checking if it's the same instance
        var retrievedOptions = runOptions.ChatOptions!;
        Assert.NotSame(chatOptions, retrievedOptions);
        Assert.Equal(100, retrievedOptions.MaxOutputTokens); // Ensure the change is not reflected
    }
}
