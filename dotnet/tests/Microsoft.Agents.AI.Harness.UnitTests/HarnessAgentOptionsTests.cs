// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Moq;
#if NET
using Microsoft.Agents.AI.Tools.Shell;
#endif

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
        Assert.Null(options.LoopEvaluators);
        Assert.Null(options.LoopAgentOptions);
        Assert.False(options.DisableToolAutoApproval);
        Assert.False(options.DisableNonApprovalRequiredFunctionBypassing);
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
        Assert.Null(options.BackgroundAgents);
        Assert.Null(options.BackgroundAgentsProviderOptions);
#if NET
        Assert.Null(options.ShellExecutor);
        Assert.Null(options.ShellEnvironmentProviderOptions);
#endif
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
        var backgroundAgents = new AIAgent[] { new Mock<AIAgent>().Object };
        var backgroundAgentsOptions = new BackgroundAgentsProviderOptions();
        var loopEvaluators = new LoopEvaluator[] { new DelegateLoopEvaluator((_, _) => new ValueTask<LoopEvaluation>(LoopEvaluation.Stop())) };
        var loopAgentOptions = new LoopAgentOptions();
#if NET
        var shellExecutor = new Mock<ShellExecutor>().Object;
        var shellEnvOptions = new ShellEnvironmentProviderOptions();
#endif

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
            DisableToolAutoApproval = true,
            DisableNonApprovalRequiredFunctionBypassing = true,
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
            BackgroundAgents = backgroundAgents,
            BackgroundAgentsProviderOptions = backgroundAgentsOptions,
            LoopEvaluators = loopEvaluators,
            LoopAgentOptions = loopAgentOptions,
#if NET
            ShellExecutor = shellExecutor,
            ShellEnvironmentProviderOptions = shellEnvOptions,
#endif
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
        Assert.True(options.DisableToolAutoApproval);
        Assert.True(options.DisableNonApprovalRequiredFunctionBypassing);
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
        Assert.Same(backgroundAgents, options.BackgroundAgents);
        Assert.Same(backgroundAgentsOptions, options.BackgroundAgentsProviderOptions);
        Assert.Same(loopEvaluators, options.LoopEvaluators);
        Assert.Same(loopAgentOptions, options.LoopAgentOptions);
#if NET
        Assert.Same(shellExecutor, options.ShellExecutor);
        Assert.Same(shellEnvOptions, options.ShellEnvironmentProviderOptions);
#endif
    }
}
