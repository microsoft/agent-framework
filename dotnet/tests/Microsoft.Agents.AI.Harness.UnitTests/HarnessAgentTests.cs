// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

public class HarnessAgentTests
{
    private const int TestMaxContextWindowTokens = 100_000;
    private const int TestMaxOutputTokens = 10_000;

    /// <summary>
    /// Creates a HarnessAgent with all default features disabled to isolate tests for specific behaviors.
    /// </summary>
    private static HarnessAgentOptions CreateAllDisabledOptions() => new()
    {
        DisableToolApproval = true,
        DisableOpenTelemetry = true,
        DisableFileMemory = true,
        DisableFileAccess = true,
        DisableWebSearch = true,
        DisableTodoProvider = true,
        DisableAgentModeProvider = true,
        DisableAgentSkillsProvider = true,
    };

    #region Constructor Validation

    /// <summary>
    /// Verify that the constructor throws when chatClient is null.
    /// </summary>
    [Fact]
    public void Constructor_ThrowsWhenChatClientIsNull()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new HarnessAgent(null!, TestMaxContextWindowTokens, TestMaxOutputTokens));
    }

    /// <summary>
    /// Verify that the constructor throws when MaxContextWindowTokens is invalid (zero).
    /// </summary>
    [Fact]
    public void Constructor_ThrowsWhenMaxContextWindowTokensIsZero()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => new HarnessAgent(chatClient, 0, TestMaxOutputTokens));
    }

    /// <summary>
    /// Verify that the constructor throws when MaxOutputTokens equals MaxContextWindowTokens.
    /// </summary>
    [Fact]
    public void Constructor_ThrowsWhenMaxOutputTokensEqualsContextWindow()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => new HarnessAgent(chatClient, 100_000, 100_000));
    }

    /// <summary>
    /// Verify that the constructor succeeds when options is null.
    /// </summary>
    [Fact]
    public void Constructor_SucceedsWhenOptionsIsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens);

        // Assert
        Assert.NotNull(agent);
    }

    #endregion

    #region Agent Identity

    /// <summary>
    /// Verify that Name and Description are passed through to the inner agent.
    /// </summary>
    [Fact]
    public void NameAndDescription_ArePassedThrough()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.Name = "TestAgent";
        options.Description = "A test agent";

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);

        // Assert
        Assert.Equal("TestAgent", agent.Name);
        Assert.Equal("A test agent", agent.Description);
    }

    /// <summary>
    /// Verify that Id is passed through to the inner agent.
    /// </summary>
    [Fact]
    public void Id_IsPassedThrough()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.Id = "my-agent-id";

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);

        // Assert
        Assert.Equal("my-agent-id", agent.Id);
    }

    #endregion

    #region Instructions

    /// <summary>
    /// Verify that default instructions are used when none are provided.
    /// </summary>
    [Fact]
    public void Instructions_DefaultsToBuiltInInstructions()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.Equal(HarnessAgent.DefaultInstructions, innerAgent!.Instructions);
    }

    /// <summary>
    /// Verify that default instructions are used when options is provided but neither HarnessInstructions nor ChatOptions.Instructions is set.
    /// </summary>
    [Fact]
    public void Instructions_DefaultsWhenBothNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.ChatOptions = new ChatOptions { Temperature = 0.5f };

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.Equal(HarnessAgent.DefaultInstructions, innerAgent!.Instructions);
    }

    /// <summary>
    /// Verify that ChatOptions.Instructions is appended to the default HarnessInstructions.
    /// </summary>
    [Fact]
    public void Instructions_CombinesDefaultHarnessWithAgentInstructions()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.ChatOptions = new ChatOptions { Instructions = "You are a custom assistant." };

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        var expected = $"{HarnessAgent.DefaultInstructions}\n\nYou are a custom assistant.";
        Assert.Equal(expected, innerAgent!.Instructions);
    }

    /// <summary>
    /// Verify that custom HarnessInstructions replaces the default.
    /// </summary>
    [Fact]
    public void Instructions_CustomHarnessInstructionsReplacesDefault()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.HarnessInstructions = "Custom harness rules.";

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.Equal("Custom harness rules.", innerAgent!.Instructions);
    }

    /// <summary>
    /// Verify that custom HarnessInstructions and ChatOptions.Instructions are combined.
    /// </summary>
    [Fact]
    public void Instructions_CombinesCustomHarnessWithAgentInstructions()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.HarnessInstructions = "Custom harness rules.";
        options.ChatOptions = new ChatOptions { Instructions = "You are a research agent." };

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.Equal("Custom harness rules.\n\nYou are a research agent.", innerAgent!.Instructions);
    }

    /// <summary>
    /// Verify that empty HarnessInstructions omits harness portion, using only agent instructions.
    /// </summary>
    [Fact]
    public void Instructions_EmptyHarnessInstructionsUsesOnlyAgentInstructions()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.HarnessInstructions = string.Empty;
        options.ChatOptions = new ChatOptions { Instructions = "Agent only instructions." };

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.Equal("Agent only instructions.", innerAgent!.Instructions);
    }

    /// <summary>
    /// Verify that empty HarnessInstructions with no agent instructions results in empty string.
    /// </summary>
    [Fact]
    public void Instructions_EmptyHarnessInstructionsWithNoAgentInstructions()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.HarnessInstructions = string.Empty;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.Equal(string.Empty, innerAgent!.Instructions);
    }

    #endregion

    #region ChatHistoryProvider

    /// <summary>
    /// Verify that the default ChatHistoryProvider is InMemoryChatHistoryProvider when none is specified.
    /// </summary>
    [Fact]
    public void ChatHistoryProvider_DefaultsToInMemory()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.IsType<InMemoryChatHistoryProvider>(innerAgent!.ChatHistoryProvider);
    }

    /// <summary>
    /// Verify that a custom ChatHistoryProvider is used when provided.
    /// </summary>
    [Fact]
    public void ChatHistoryProvider_UsesCustomProviderWhenSpecified()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var customProvider = new InMemoryChatHistoryProvider();
        var options = CreateAllDisabledOptions();
        options.ChatHistoryProvider = customProvider;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.Same(customProvider, innerAgent!.ChatHistoryProvider);
    }

    #endregion

    #region ChatClient Pipeline

    /// <summary>
    /// Verify that the inner agent's ChatClient includes FunctionInvokingChatClient in the pipeline.
    /// </summary>
    [Fact]
    public void Pipeline_IncludesFunctionInvokingChatClient()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        var ficc = innerAgent!.ChatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(ficc);
    }

    /// <summary>
    /// Verify that the inner agent's ChatClient pipeline includes more than just the raw chat client,
    /// confirming that per-service-call persistence and other decorators have been applied.
    /// </summary>
    [Fact]
    public void Pipeline_HasDecoratedChatClient()
    {
        // Arrange
        var mockClient = new Mock<IChatClient>();
        var rawClient = mockClient.Object;

        // Act
        var agent = new HarnessAgent(rawClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert — the pipeline wraps the raw client, so the outer client is not the same object.
        Assert.NotNull(innerAgent);
        Assert.NotSame(rawClient, innerAgent!.ChatClient);
    }

    #endregion

    #region AIContextProviders

    /// <summary>
    /// Verify that additional AIContextProviders from options are passed to the inner ChatClientAgent.
    /// </summary>
    [Fact]
    public void AIContextProviders_ArePassedToInnerAgent()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var customProvider = new TodoProvider();
        var options = CreateAllDisabledOptions();
        options.AIContextProviders = [customProvider];

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert — the custom provider should appear in the inner agent's AIContextProviders.
        Assert.NotNull(innerAgent);
        Assert.NotNull(innerAgent!.AIContextProviders);
        Assert.Contains(customProvider, innerAgent.AIContextProviders!);
    }

    /// <summary>
    /// Verify that when all default providers are disabled and no user AIContextProviders are specified,
    /// the inner agent has an empty providers list.
    /// </summary>
    [Fact]
    public void AIContextProviders_IsEmptyWhenAllDisabledAndNoneSpecified()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.NotNull(innerAgent!.AIContextProviders);
        Assert.Empty(innerAgent.AIContextProviders!);
    }

    #endregion

    #region ChatOptions and Tools

    /// <summary>
    /// Verify that tools from ChatOptions are passed to the model during invocation.
    /// </summary>
    [Fact]
    public async Task ChatOptions_ToolsArePreservedAsync()
    {
        // Arrange
        var tool = AIFunctionFactory.Create(() => "test", "TestTool");
        var mockClient = new Mock<IChatClient>();
        ChatOptions? capturedOptions = null;
        mockClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Done")));

        var options = CreateAllDisabledOptions();
        options.ChatOptions = new ChatOptions { Tools = [tool] };

        var agent = new HarnessAgent(mockClient.Object, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);

        // Assert — verify the tool was included in the ChatOptions passed to the model.
        Assert.NotNull(capturedOptions);
        Assert.NotNull(capturedOptions!.Tools);
        Assert.Contains(capturedOptions.Tools, t => t == tool);
    }

    /// <summary>
    /// Verify that the source ChatOptions are cloned and not modified.
    /// </summary>
    [Fact]
    public void ChatOptions_SourceIsNotModified()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var sourceChatOptions = new ChatOptions
        {
            Instructions = "original instructions",
            Temperature = 0.7f,
        };

        // Act
        _ = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, new HarnessAgentOptions
        {
            ChatOptions = sourceChatOptions,
        });

        // Assert — source ChatOptions should not be mutated.
        Assert.Equal("original instructions", sourceChatOptions.Instructions);
        Assert.Equal(0.7f, sourceChatOptions.Temperature);
    }

    #endregion

    #region GetService

    /// <summary>
    /// Verify that GetService returns the HarnessAgent for its own type.
    /// </summary>
    [Fact]
    public void GetService_ReturnsSelfForHarnessAgentType()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());

        // Assert
        Assert.Same(agent, agent.GetService<HarnessAgent>());
    }

    /// <summary>
    /// Verify that GetService returns the inner ChatClientAgent.
    /// </summary>
    [Fact]
    public void GetService_ReturnsInnerChatClientAgent()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());

        // Assert
        Assert.NotNull(agent.GetService<ChatClientAgent>());
    }

    #endregion

    #region RunAsync Delegation

    /// <summary>
    /// Verify that RunAsync delegates to the inner ChatClientAgent.
    /// </summary>
    [Fact]
    public async Task RunAsync_DelegatesToInnerAgentAsync()
    {
        // Arrange
        var mockClient = new Mock<IChatClient>();
        mockClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Hello!")));

        var agent = new HarnessAgent(mockClient.Object, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var session = await agent.CreateSessionAsync();

        // Act
        var response = await agent.RunAsync(
            [new ChatMessage(ChatRole.User, "Hi")],
            session);

        // Assert
        Assert.NotNull(response);
        Assert.True(response.Messages.Any());
    }

    #endregion

    #region DefaultInstructions

    /// <summary>
    /// Verify that DefaultInstructions is a non-empty public constant.
    /// </summary>
    [Fact]
    public void DefaultInstructions_IsNonEmpty()
    {
        // Assert
        Assert.False(string.IsNullOrWhiteSpace(HarnessAgent.DefaultInstructions));
    }

    #endregion

    #region AsHarnessAgent Extension Method

    /// <summary>
    /// Verify that AsHarnessAgent creates a HarnessAgent with default options.
    /// </summary>
    [Fact]
    public void AsHarnessAgent_CreatesAgentWithDefaults()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = chatClient.AsHarnessAgent(TestMaxContextWindowTokens, TestMaxOutputTokens);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<HarnessAgent>(agent);
        Assert.Equal(HarnessAgent.DefaultInstructions, agent.GetService<ChatClientAgent>()!.Instructions);
    }

    /// <summary>
    /// Verify that AsHarnessAgent passes options through to the HarnessAgent.
    /// </summary>
    [Fact]
    public void AsHarnessAgent_PassesOptionsThrough()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.Name = "ExtensionAgent";
        options.ChatOptions = new ChatOptions { Instructions = "Custom instructions" };

        // Act
        var agent = chatClient.AsHarnessAgent(TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.Equal("ExtensionAgent", agent.Name);
        Assert.NotNull(innerAgent);
        var expected = $"{HarnessAgent.DefaultInstructions}\n\nCustom instructions";
        Assert.Equal(expected, innerAgent!.Instructions);
    }

    /// <summary>
    /// Verify that AsHarnessAgent throws when chatClient is null.
    /// </summary>
    [Fact]
    public void AsHarnessAgent_ThrowsWhenChatClientIsNull()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => ((IChatClient)null!).AsHarnessAgent(TestMaxContextWindowTokens, TestMaxOutputTokens));
    }

    #endregion

    #region Feature: ToolApproval

    /// <summary>
    /// Verify that ToolApprovalAgent is included in the pipeline by default.
    /// </summary>
    [Fact]
    public void ToolApproval_IncludedByDefault()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableToolApproval = false;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);

        // Assert
        Assert.NotNull(agent.GetService<ToolApprovalAgent>());
    }

    /// <summary>
    /// Verify that ToolApprovalAgent is excluded when disabled.
    /// </summary>
    [Fact]
    public void ToolApproval_ExcludedWhenDisabled()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());

        // Assert
        Assert.Null(agent.GetService<ToolApprovalAgent>());
    }

    #endregion

    #region Feature: OpenTelemetry

    /// <summary>
    /// Verify that OpenTelemetryAgent is included in the pipeline by default.
    /// </summary>
    [Fact]
    public void OpenTelemetry_IncludedByDefault()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableOpenTelemetry = false;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);

        // Assert
        Assert.NotNull(agent.GetService<OpenTelemetryAgent>());
    }

    /// <summary>
    /// Verify that OpenTelemetryAgent is excluded when disabled.
    /// </summary>
    [Fact]
    public void OpenTelemetry_ExcludedWhenDisabled()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());

        // Assert
        Assert.Null(agent.GetService<OpenTelemetryAgent>());
    }

    /// <summary>
    /// Verify that a custom OpenTelemetrySourceName is accepted without error.
    /// </summary>
    [Fact]
    public void OpenTelemetry_CustomSourceNameIsAccepted()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableOpenTelemetry = false;
        options.OpenTelemetrySourceName = "MyApp.AgentTracing";

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);

        // Assert
        Assert.NotNull(agent.GetService<OpenTelemetryAgent>());
    }

    #endregion

    #region Feature: WebSearch

    /// <summary>
    /// Verify that HostedWebSearchTool is added to ChatOptions.Tools by default.
    /// </summary>
    [Fact]
    public async Task WebSearch_IncludedByDefaultAsync()
    {
        // Arrange
        var mockClient = new Mock<IChatClient>();
        ChatOptions? capturedOptions = null;
        mockClient
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Done")));

        var options = CreateAllDisabledOptions();
        options.DisableWebSearch = false;

        var agent = new HarnessAgent(mockClient.Object, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);

        // Assert
        Assert.NotNull(capturedOptions?.Tools);
        Assert.Contains(capturedOptions!.Tools!, t => t is HostedWebSearchTool);
    }

    /// <summary>
    /// Verify that HostedWebSearchTool is not added when disabled.
    /// </summary>
    [Fact]
    public async Task WebSearch_ExcludedWhenDisabledAsync()
    {
        // Arrange
        var mockClient = new Mock<IChatClient>();
        ChatOptions? capturedOptions = null;
        mockClient
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Done")));

        var agent = new HarnessAgent(mockClient.Object, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);

        // Assert
        Assert.NotNull(capturedOptions);
        if (capturedOptions!.Tools != null)
        {
            Assert.DoesNotContain(capturedOptions.Tools, t => t is HostedWebSearchTool);
        }
    }

    /// <summary>
    /// Verify that user-provided tools are preserved alongside the default HostedWebSearchTool.
    /// </summary>
    [Fact]
    public async Task WebSearch_CoexistsWithUserToolsAsync()
    {
        // Arrange
        var mockClient = new Mock<IChatClient>();
        ChatOptions? capturedOptions = null;
        mockClient
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Done")));

        var userTool = AIFunctionFactory.Create(() => "test", "UserTool");
        var options = CreateAllDisabledOptions();
        options.DisableWebSearch = false;
        options.ChatOptions = new ChatOptions { Tools = [userTool] };

        var agent = new HarnessAgent(mockClient.Object, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);

        // Assert
        Assert.NotNull(capturedOptions?.Tools);
        Assert.Contains(capturedOptions!.Tools!, t => t is HostedWebSearchTool);
        Assert.Contains(capturedOptions.Tools!, t => t == userTool);
    }

    #endregion

    #region Feature: TodoProvider

    /// <summary>
    /// Verify that TodoProvider is included in AIContextProviders by default.
    /// </summary>
    [Fact]
    public void TodoProvider_IncludedByDefault()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableTodoProvider = false;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent?.AIContextProviders);
        Assert.Contains(innerAgent!.AIContextProviders!, p => p is TodoProvider);
    }

    /// <summary>
    /// Verify that TodoProvider is excluded when disabled.
    /// </summary>
    [Fact]
    public void TodoProvider_ExcludedWhenDisabled()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        if (innerAgent!.AIContextProviders != null)
        {
            Assert.DoesNotContain(innerAgent.AIContextProviders, p => p is TodoProvider);
        }
    }

    #endregion

    #region Feature: AgentModeProvider

    /// <summary>
    /// Verify that AgentModeProvider is included in AIContextProviders by default.
    /// </summary>
    [Fact]
    public void AgentModeProvider_IncludedByDefault()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableAgentModeProvider = false;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent?.AIContextProviders);
        Assert.Contains(innerAgent!.AIContextProviders!, p => p is AgentModeProvider);
    }

    /// <summary>
    /// Verify that AgentModeProvider is excluded when disabled.
    /// </summary>
    [Fact]
    public void AgentModeProvider_ExcludedWhenDisabled()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        if (innerAgent!.AIContextProviders != null)
        {
            Assert.DoesNotContain(innerAgent.AIContextProviders, p => p is AgentModeProvider);
        }
    }

    /// <summary>
    /// Verify that custom AgentModeProviderOptions are passed through.
    /// </summary>
    [Fact]
    public void AgentModeProvider_UsesCustomOptions()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableAgentModeProvider = false;
        options.AgentModeProviderOptions = new AgentModeProviderOptions
        {
            Modes =
            [
                new AgentModeProviderOptions.AgentMode("custom-mode", "A custom mode for testing"),
            ],
            DefaultMode = "custom-mode",
        };

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert — AgentModeProvider should be present (we can't easily inspect its internal options,
        // but we verify it is created and present).
        Assert.NotNull(innerAgent?.AIContextProviders);
        Assert.Contains(innerAgent!.AIContextProviders!, p => p is AgentModeProvider);
    }

    #endregion

    #region Feature: FileMemoryProvider

    /// <summary>
    /// Verify that FileMemoryProvider is included in AIContextProviders by default.
    /// </summary>
    [Fact]
    public void FileMemoryProvider_IncludedByDefault()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableFileMemory = false;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent?.AIContextProviders);
        Assert.Contains(innerAgent!.AIContextProviders!, p => p is FileMemoryProvider);
    }

    /// <summary>
    /// Verify that FileMemoryProvider is excluded when disabled.
    /// </summary>
    [Fact]
    public void FileMemoryProvider_ExcludedWhenDisabled()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        if (innerAgent!.AIContextProviders != null)
        {
            Assert.DoesNotContain(innerAgent.AIContextProviders, p => p is FileMemoryProvider);
        }
    }

    /// <summary>
    /// Verify that a custom FileMemoryStore is used when provided.
    /// </summary>
    [Fact]
    public void FileMemoryProvider_UsesCustomStore()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var customStore = new Mock<AgentFileStore>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableFileMemory = false;
        options.FileMemoryStore = customStore;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert — FileMemoryProvider should be present with the custom store.
        Assert.NotNull(innerAgent?.AIContextProviders);
        Assert.Contains(innerAgent!.AIContextProviders!, p => p is FileMemoryProvider);
    }

    #endregion

    #region Feature: FileAccessProvider

    /// <summary>
    /// Verify that FileAccessProvider is included in AIContextProviders by default.
    /// </summary>
    [Fact]
    public void FileAccessProvider_IncludedByDefault()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableFileAccess = false;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent?.AIContextProviders);
        Assert.Contains(innerAgent!.AIContextProviders!, p => p is FileAccessProvider);
    }

    /// <summary>
    /// Verify that FileAccessProvider is excluded when disabled.
    /// </summary>
    [Fact]
    public void FileAccessProvider_ExcludedWhenDisabled()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        if (innerAgent!.AIContextProviders != null)
        {
            Assert.DoesNotContain(innerAgent.AIContextProviders, p => p is FileAccessProvider);
        }
    }

    /// <summary>
    /// Verify that a custom FileAccessStore is used when provided.
    /// </summary>
    [Fact]
    public void FileAccessProvider_UsesCustomStore()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var customStore = new Mock<AgentFileStore>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableFileAccess = false;
        options.FileAccessStore = customStore;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert — FileAccessProvider should be present with the custom store.
        Assert.NotNull(innerAgent?.AIContextProviders);
        Assert.Contains(innerAgent!.AIContextProviders!, p => p is FileAccessProvider);
    }

    #endregion

    #region Feature: AgentSkillsProvider

    /// <summary>
    /// Verify that AgentSkillsProvider is included in AIContextProviders by default.
    /// </summary>
    [Fact]
    public void AgentSkillsProvider_IncludedByDefault()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableAgentSkillsProvider = false;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent?.AIContextProviders);
        Assert.Contains(innerAgent!.AIContextProviders!, p => p is AgentSkillsProvider);
    }

    /// <summary>
    /// Verify that AgentSkillsProvider is excluded when disabled.
    /// </summary>
    [Fact]
    public void AgentSkillsProvider_ExcludedWhenDisabled()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        if (innerAgent!.AIContextProviders != null)
        {
            Assert.DoesNotContain(innerAgent.AIContextProviders, p => p is AgentSkillsProvider);
        }
    }

    /// <summary>
    /// Verify that a custom AgentSkillsSource is used when provided.
    /// </summary>
    [Fact]
    public void AgentSkillsProvider_UsesCustomSource()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var customSource = new Mock<AgentSkillsSource>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableAgentSkillsProvider = false;
        options.AgentSkillsSource = customSource;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert — AgentSkillsProvider should be present.
        Assert.NotNull(innerAgent?.AIContextProviders);
        Assert.Contains(innerAgent!.AIContextProviders!, p => p is AgentSkillsProvider);
    }

    #endregion

    #region Feature: MaximumIterationsPerRequest

    /// <summary>
    /// Verify that MaximumIterationsPerRequest configures the FunctionInvokingChatClient.
    /// </summary>
    [Fact]
    public void MaximumIterationsPerRequest_ConfiguresFunctionInvokingChatClient()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.MaximumIterationsPerRequest = 42;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, options);
        var innerAgent = agent.GetService<ChatClientAgent>();
        var ficc = innerAgent!.ChatClient.GetService<FunctionInvokingChatClient>();

        // Assert
        Assert.NotNull(ficc);
        Assert.Equal(42, ficc!.MaximumIterationsPerRequest);
    }

    /// <summary>
    /// Verify that the default MaximumIterationsPerRequest is used when not set.
    /// </summary>
    [Fact]
    public void MaximumIterationsPerRequest_UsesDefaultWhenNotSet()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, TestMaxContextWindowTokens, TestMaxOutputTokens, CreateAllDisabledOptions());
        var innerAgent = agent.GetService<ChatClientAgent>();
        var ficc = innerAgent!.ChatClient.GetService<FunctionInvokingChatClient>();

        // Assert — default is not 0 and not our custom value.
        Assert.NotNull(ficc);
        Assert.NotEqual(0, ficc!.MaximumIterationsPerRequest);
    }

    #endregion

    #region Feature: All Defaults Enabled

    /// <summary>
    /// Verify that when no options are provided, all default features are enabled.
    /// </summary>
    [Fact]
    public async Task AllDefaults_AllFeaturesEnabledAsync()
    {
        // Arrange
        var mockClient = new Mock<IChatClient>();
        ChatOptions? capturedOptions = null;
        mockClient
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "Done")));

        // Act
        var agent = new HarnessAgent(mockClient.Object, TestMaxContextWindowTokens, TestMaxOutputTokens);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert — agent wrappers
        Assert.NotNull(agent.GetService<ToolApprovalAgent>());
        Assert.NotNull(agent.GetService<OpenTelemetryAgent>());

        // Assert — default context providers
        Assert.NotNull(innerAgent);
        Assert.NotNull(innerAgent!.AIContextProviders);

        var providers = innerAgent.AIContextProviders!.ToList();
        Assert.Contains(providers, p => p is TodoProvider);
        Assert.Contains(providers, p => p is AgentModeProvider);
        Assert.Contains(providers, p => p is FileMemoryProvider);
        Assert.Contains(providers, p => p is FileAccessProvider);
        Assert.Contains(providers, p => p is AgentSkillsProvider);

        // Assert — HostedWebSearchTool is present in the tools sent to the model
        var session = await agent.CreateSessionAsync();
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);
        Assert.NotNull(capturedOptions?.Tools);
        Assert.Contains(capturedOptions!.Tools!, t => t is HostedWebSearchTool);
    }

    #endregion
}
