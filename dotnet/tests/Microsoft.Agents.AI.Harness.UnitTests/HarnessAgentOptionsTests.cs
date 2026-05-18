// Copyright (c) Microsoft. All rights reserved.

using Moq;

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
        Assert.Null(options.HarnessInstructions);
        Assert.Null(options.ChatHistoryProvider);
        Assert.Null(options.AIContextProviders);
        Assert.False(options.DisableToolApproval);
        Assert.False(options.DisableFileMemory);
        Assert.False(options.DisableFileAccess);
        Assert.False(options.DisableWebSearch);
        Assert.False(options.DisableTodoProvider);
        Assert.False(options.DisableAgentModeProvider);
        Assert.False(options.DisableAgentSkillsProvider);
        Assert.False(options.DisableOpenTelemetry);
        Assert.Null(options.OpenTelemetrySourceName);
        Assert.Null(options.MaximumIterationsPerRequest);
        Assert.Null(options.FileMemoryStore);
        Assert.Null(options.FileAccessStore);
        Assert.Null(options.AgentModeProviderOptions);
        Assert.Null(options.AgentSkillsSource);
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
        var fileMemoryStore = new Mock<AgentFileStore>().Object;
        var fileAccessStore = new Mock<AgentFileStore>().Object;
        var agentModeOptions = new AgentModeProviderOptions();
        var skillsSource = new Mock<AgentSkillsSource>().Object;

        // Act
        var options = new HarnessAgentOptions
        {
            Id = "test-id",
            Name = "test-name",
            Description = "test-description",
            ChatOptions = new() { Temperature = 0.5f, Instructions = "custom instructions" },
            HarnessInstructions = "custom harness instructions",
            ChatHistoryProvider = chatHistoryProvider,
            AIContextProviders = contextProviders,
            MaximumIterationsPerRequest = 42,
            DisableToolApproval = true,
            DisableFileMemory = true,
            FileMemoryStore = fileMemoryStore,
            DisableFileAccess = true,
            FileAccessStore = fileAccessStore,
            DisableWebSearch = true,
            DisableTodoProvider = true,
            DisableAgentModeProvider = true,
            AgentModeProviderOptions = agentModeOptions,
            DisableAgentSkillsProvider = true,
            AgentSkillsSource = skillsSource,
            DisableOpenTelemetry = true,
            OpenTelemetrySourceName = "custom-source",
        };

        // Assert
        Assert.Equal("test-id", options.Id);
        Assert.Equal("test-name", options.Name);
        Assert.Equal("test-description", options.Description);
        Assert.NotNull(options.ChatOptions);
        Assert.Equal(0.5f, options.ChatOptions!.Temperature);
        Assert.Equal("custom instructions", options.ChatOptions.Instructions);
        Assert.Equal("custom harness instructions", options.HarnessInstructions);
        Assert.Same(chatHistoryProvider, options.ChatHistoryProvider);
        Assert.Same(contextProviders, options.AIContextProviders);
        Assert.Equal(42, options.MaximumIterationsPerRequest);
        Assert.True(options.DisableToolApproval);
        Assert.True(options.DisableFileMemory);
        Assert.Same(fileMemoryStore, options.FileMemoryStore);
        Assert.True(options.DisableFileAccess);
        Assert.Same(fileAccessStore, options.FileAccessStore);
        Assert.True(options.DisableWebSearch);
        Assert.True(options.DisableTodoProvider);
        Assert.True(options.DisableAgentModeProvider);
        Assert.Same(agentModeOptions, options.AgentModeProviderOptions);
        Assert.True(options.DisableAgentSkillsProvider);
        Assert.Same(skillsSource, options.AgentSkillsSource);
        Assert.True(options.DisableOpenTelemetry);
        Assert.Equal("custom-source", options.OpenTelemetrySourceName);
    }
}
