// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.UnitTests;

public class HarnessAgentOptionsTests
{
    /// <summary>
    /// Verify that default property values are as expected.
    /// </summary>
    [Fact]
    public void DefaultPropertyValues()
    {
        // Arrange & Act
        var options = new HarnessAgentOptions();

        // Assert
        Assert.Null(options.Id);
        Assert.Null(options.Name);
        Assert.Null(options.Description);
        Assert.Null(options.ChatOptions);
        Assert.Null(options.ChatHistoryProvider);
        Assert.Null(options.AIContextProviders);
    }

    /// <summary>
    /// Verify that all properties can be set and retrieved.
    /// </summary>
    [Fact]
    public void PropertiesCanBeSetAndRetrieved()
    {
        // Arrange
        var chatHistoryProvider = new InMemoryChatHistoryProvider();
        var contextProviders = new AIContextProvider[] { new TodoProvider() };

        // Act
        var options = new HarnessAgentOptions
        {
            Id = "test-id",
            Name = "test-name",
            Description = "test-description",
            ChatOptions = new() { Temperature = 0.5f, Instructions = "custom instructions" },
            ChatHistoryProvider = chatHistoryProvider,
            AIContextProviders = contextProviders,
        };

        // Assert
        Assert.Equal("test-id", options.Id);
        Assert.Equal("test-name", options.Name);
        Assert.Equal("test-description", options.Description);
        Assert.NotNull(options.ChatOptions);
        Assert.Equal(0.5f, options.ChatOptions!.Temperature);
        Assert.Equal("custom instructions", options.ChatOptions.Instructions);
        Assert.Same(chatHistoryProvider, options.ChatHistoryProvider);
        Assert.Same(contextProviders, options.AIContextProviders);
    }
}
