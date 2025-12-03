// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Unit tests for the <see cref="ChatClientAgentOptions"/> class.
/// </summary>
public class ChatClientAgentOptionsTests
{
    [Fact]
    public void DefaultConstructor_InitializesWithNullValues()
    {
        // Act
        var options = new ChatClientAgentOptions();

        // Assert
        Assert.Null(options.Name);
        Assert.Null(options.Description);
        Assert.Null(options.ChatOptions);
        Assert.Null(options.ChatMessageStoreFactory);
        Assert.Null(options.AIContextProviderFactory);
    }

    [Fact]
    public void Constructor_WithNullValues_SetsPropertiesCorrectly()
    {
        // Act
        var options = new ChatClientAgentOptions() { Name = null, Description = null, ChatOptions = new() { Tools = null, Instructions = null } };

        // Assert
        Assert.Null(options.Name);
        Assert.Null(options.Description);
        Assert.Null(options.AIContextProviderFactory);
        Assert.Null(options.ChatMessageStoreFactory);
        Assert.NotNull(options.ChatOptions);
        Assert.Null(options.ChatOptions.Instructions);
        Assert.Null(options.ChatOptions.Tools);
    }

    [Fact]
    public void Constructor_WithToolsOnly_SetsChatOptionsWithTools()
    {
        // Arrange
        var tools = new List<AITool> { AIFunctionFactory.Create(() => "test") };

        // Act
        var options = new ChatClientAgentOptions()
        {
            Name = null,
            Description = null,
            ChatOptions = new() { Tools = tools }
        };

        // Assert
        Assert.Null(options.Name);
        Assert.Null(options.Description);
        Assert.NotNull(options.ChatOptions);
        AssertSameTools(tools, options.ChatOptions.Tools);
    }

    [Fact]
    public void Constructor_WithAllParameters_SetsAllPropertiesCorrectly()
    {
        // Arrange
        const string Instructions = "Test instructions";
        const string Name = "Test name";
        const string Description = "Test description";
        var tools = new List<AITool> { AIFunctionFactory.Create(() => "test") };

        // Act
        var options = new ChatClientAgentOptions()
        {
            Name = Name,
            Description = Description,
            ChatOptions = new() { Tools = tools, Instructions = Instructions }
        };

        // Assert
        Assert.Equal(Name, options.Name);
        Assert.Equal(Instructions, options.ChatOptions.Instructions);
        Assert.Equal(Description, options.Description);
        Assert.NotNull(options.ChatOptions);
        AssertSameTools(tools, options.ChatOptions.Tools);
    }

    [Fact]
    public void Constructor_WithNameAndDescriptionOnly_DoesNotCreateChatOptions()
    {
        // Arrange
        const string Name = "Test name";
        const string Description = "Test description";

        // Act
        var options = new ChatClientAgentOptions()
        {
            Name = Name,
            Description = Description,
        };

        // Assert
        Assert.Equal(Name, options.Name);
        Assert.Equal(Description, options.Description);
        Assert.Null(options.ChatOptions);
    }

    [Fact]
    public void Clone_CreatesDeepCopyWithSameValues()
    {
        // Arrange
        const string Name = "Test name";
        const string Description = "Test description";
        var tools = new List<AITool> { AIFunctionFactory.Create(() => "test") };

        static ChatMessageStore ChatMessageStoreFactory(
            ChatClientAgentOptions.ChatMessageStoreFactoryContext ctx) => new Mock<ChatMessageStore>().Object;

        static AIContextProvider AIContextProviderFactory(
            ChatClientAgentOptions.AIContextProviderFactoryContext ctx) =>
            new Mock<AIContextProvider>().Object;

        var original = new ChatClientAgentOptions()
        {
            Name = Name,
            Description = Description,
            ChatOptions = new() { Tools = tools },
            Id = "test-id",
            ChatMessageStoreFactory = ChatMessageStoreFactory,
            AIContextProviderFactory = AIContextProviderFactory
        };

        // Act
        var clone = original.Clone();

        // Assert
        Assert.NotSame(original, clone);
        Assert.Equal(original.Id, clone.Id);
        Assert.Equal(original.Name, clone.Name);
        Assert.Equal(original.Description, clone.Description);
        Assert.Same(original.ChatMessageStoreFactory, clone.ChatMessageStoreFactory);
        Assert.Same(original.AIContextProviderFactory, clone.AIContextProviderFactory);

        // ChatOptions should be cloned, not the same reference
        Assert.NotSame(original.ChatOptions, clone.ChatOptions);
        Assert.Equal(original.ChatOptions?.Instructions, clone.ChatOptions?.Instructions);
        Assert.Equal(original.ChatOptions?.Tools, clone.ChatOptions?.Tools);
    }

    [Fact]
    public void Clone_WithoutProvidingChatOptions_ClonesCorrectly()
    {
        // Arrange
        var original = new ChatClientAgentOptions
        {
            Id = "test-id",
            Name = "Test name",
            Description = "Test description"
        };

        // Act
        var clone = original.Clone();

        // Assert
        Assert.NotSame(original, clone);
        Assert.Equal(original.Id, clone.Id);
        Assert.Equal(original.Name, clone.Name);
        Assert.Equal(original.Description, clone.Description);
        Assert.Null(original.ChatOptions);
        Assert.Null(clone.ChatMessageStoreFactory);
        Assert.Null(clone.AIContextProviderFactory);
    }

    private static void AssertSameTools(IList<AITool>? expected, IList<AITool>? actual)
    {
        var index = 0;
        foreach (var tool in expected ?? [])
        {
            Assert.Same(tool, actual?[index]);
            index++;
        }
    }
}
