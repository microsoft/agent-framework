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
        Assert.Null(options.ChatHistoryProvider);
        Assert.Null(options.AIContextProviders);
        Assert.False(options.UseProvidedChatClientAsIs);
        Assert.True(options.ClearOnChatHistoryProviderConflict);
        Assert.True(options.WarnOnChatHistoryProviderConflict);
        Assert.True(options.ThrowOnChatHistoryProviderConflict);
    }

    [Fact]
    public void Constructor_WithNullValues_SetsPropertiesCorrectly()
    {
        // Act
        var options = new ChatClientAgentOptions() { Name = null, Description = null, ChatOptions = new() { Tools = null, Instructions = null } };

        // Assert
        Assert.Null(options.Name);
        Assert.Null(options.Description);
        Assert.Null(options.AIContextProviders);
        Assert.Null(options.ChatHistoryProvider);
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

        var mockChatHistoryProvider = new Mock<ChatHistoryProvider>(null, null).Object;
        var mockAIContextProvider = new Mock<AIContextProvider>(null, null).Object;

        var original = new ChatClientAgentOptions()
        {
            Name = Name,
            Description = Description,
            ChatOptions = new() { Tools = tools },
            Id = "test-id",
            ChatHistoryProvider = mockChatHistoryProvider,
            AIContextProviders = [mockAIContextProvider],
            UseProvidedChatClientAsIs = true,
            ClearOnChatHistoryProviderConflict = false,
            WarnOnChatHistoryProviderConflict = false,
            ThrowOnChatHistoryProviderConflict = false,
        };

        // Act
        var clone = original.Clone();

        // Assert
        Assert.NotSame(original, clone);
        Assert.Equal(original.Id, clone.Id);
        Assert.Equal(original.Name, clone.Name);
        Assert.Equal(original.Description, clone.Description);
        Assert.Same(original.ChatHistoryProvider, clone.ChatHistoryProvider);
        Assert.Equal(original.AIContextProviders, clone.AIContextProviders);
        Assert.Equal(original.UseProvidedChatClientAsIs, clone.UseProvidedChatClientAsIs);
        Assert.Equal(original.ClearOnChatHistoryProviderConflict, clone.ClearOnChatHistoryProviderConflict);
        Assert.Equal(original.WarnOnChatHistoryProviderConflict, clone.WarnOnChatHistoryProviderConflict);
        Assert.Equal(original.ThrowOnChatHistoryProviderConflict, clone.ThrowOnChatHistoryProviderConflict);

        // ChatOptions should be cloned, not the same reference
        Assert.NotSame(original.ChatOptions, clone.ChatOptions);
        Assert.Equal(original.ChatOptions?.Instructions, clone.ChatOptions?.Instructions);
        Assert.Equal(original.ChatOptions?.Tools, clone.ChatOptions?.Tools);
    }

    [Fact]
    public void Clone_WithoutProvidingChatOptions_ClonesCorrectly()
    {
        // Arrange
        var mockChatHistoryProvider = new Mock<ChatHistoryProvider>(null, null).Object;
        var mockAIContextProvider = new Mock<AIContextProvider>(null, null).Object;

        var original = new ChatClientAgentOptions
        {
            Id = "test-id",
            Name = "Test name",
            Description = "Test description",
            ChatHistoryProvider = mockChatHistoryProvider,
            AIContextProviders = [mockAIContextProvider]
        };

        // Act
        var clone = original.Clone();

        // Assert
        Assert.NotSame(original, clone);
        Assert.Equal(original.Id, clone.Id);
        Assert.Equal(original.Name, clone.Name);
        Assert.Equal(original.Description, clone.Description);
        Assert.Null(original.ChatOptions);
        Assert.Same(original.ChatHistoryProvider, clone.ChatHistoryProvider);
        Assert.Equal(original.AIContextProviders, clone.AIContextProviders);
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
