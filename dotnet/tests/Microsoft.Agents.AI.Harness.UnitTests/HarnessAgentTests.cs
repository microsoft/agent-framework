// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
#if NET
using Microsoft.Agents.AI.Tools.Shell;
#endif
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Logging;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

public class HarnessAgentTests
{
    private const int TestMaxContextWindowTokens = 100_000;
    private const int TestMaxOutputTokens = 10_000;

    /// <summary>
    /// Creates a HarnessAgent with all default features disabled to isolate tests for specific behaviors.
    /// Compaction is enabled by default for backward compatibility with existing tests.
    /// </summary>
    private static HarnessAgentOptions CreateAllDisabledOptions() => new()
    {
        MaxContextWindowTokens = TestMaxContextWindowTokens,
        MaxOutputTokens = TestMaxOutputTokens,
        DisableToolAutoApproval = true,
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
        Assert.Throws<ArgumentNullException>(() => new HarnessAgent(null!));
    }

    /// <summary>
    /// Verify that the constructor throws when MaxContextWindowTokens is invalid (zero).
    /// </summary>
    [Fact]
    public void Constructor_ThrowsWhenMaxContextWindowTokensIsZero()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = new HarnessAgentOptions { MaxContextWindowTokens = 0, MaxOutputTokens = TestMaxOutputTokens };

        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => new HarnessAgent(chatClient, options));
    }

    /// <summary>
    /// Verify that the constructor throws when MaxOutputTokens equals MaxContextWindowTokens.
    /// </summary>
    [Fact]
    public void Constructor_ThrowsWhenMaxOutputTokensEqualsContextWindow()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = new HarnessAgentOptions { MaxContextWindowTokens = 100_000, MaxOutputTokens = 100_000 };

        // Act & Assert
        Assert.Throws<ArgumentOutOfRangeException>(() => new HarnessAgent(chatClient, options));
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
        var agent = new HarnessAgent(chatClient);

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
        var agent = new HarnessAgent(chatClient, options);

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
        var agent = new HarnessAgent(chatClient, options);

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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());
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
        var agent = new HarnessAgent(rawClient, CreateAllDisabledOptions());
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());
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

        var agent = new HarnessAgent(mockClient.Object, options);
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
        _ = new HarnessAgent(chatClient, new HarnessAgentOptions
        {
            MaxContextWindowTokens = TestMaxContextWindowTokens,
            MaxOutputTokens = TestMaxOutputTokens,
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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());

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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());

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

        var agent = new HarnessAgent(mockClient.Object, CreateAllDisabledOptions());
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
        var agent = chatClient.AsHarnessAgent();

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
        var agent = chatClient.AsHarnessAgent(options);
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
        Assert.Throws<ArgumentNullException>(() => ((IChatClient)null!).AsHarnessAgent());
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
        options.DisableToolAutoApproval = false;

        // Act
        var agent = new HarnessAgent(chatClient, options);

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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());

        // Assert
        Assert.Null(agent.GetService<ToolApprovalAgent>());
    }

    /// <summary>
    /// Verify that ToolApprovalAgentOptions auto-approval rules are passed through and actually used.
    /// </summary>
    [Fact]
    public async Task ToolApproval_AutoApprovalRulesAreAppliedAsync()
    {
        // Arrange — inner client returns an approval request on first call, then final response on second.
        var callCount = 0;
        var approvalRequest = new ToolApprovalRequestContent("req1", new FunctionCallContent("call1", "ReadTool"));

        var mockClient = new Mock<IChatClient>();
        mockClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(() =>
            {
                callCount++;
                if (callCount == 1)
                {
                    return new ChatResponse(new ChatMessage(ChatRole.Assistant, [approvalRequest]));
                }

                return new ChatResponse(new ChatMessage(ChatRole.Assistant, "Done"));
            });

        var options = CreateAllDisabledOptions();
        options.DisableToolAutoApproval = false;
        options.ToolApprovalAgentOptions = new ToolApprovalAgentOptions
        {
            AutoApprovalRules = [fcc => new ValueTask<bool>(fcc.Name == "ReadTool")]
        };

        var agent = new HarnessAgent(mockClient.Object, options);
        var session = await agent.CreateSessionAsync();

        // Act
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);

        // Assert — the auto-approval rule approved the request, so we get "Done" (not an approval request)
        Assert.Equal(2, callCount);
        Assert.Equal("Done", response.Text);
    }

    #endregion

    #region Feature: NonApprovalRequiredFunctionBypassing

    /// <summary>
    /// Verify that by default, when a response contains a mix of tools that require approval and tools that do not,
    /// only the approval-required tool is surfaced to the caller. The non-approval-required tool is bypassed
    /// (stored as auto-approved) by the <c>NonApprovalRequiredFunctionBypassingChatClient</c> decorator.
    /// </summary>
    [Fact]
    public async Task NonApprovalRequiredFunctionBypassing_BypassesNonApprovalToolsByDefaultAsync()
    {
        // Arrange — the model requests both a normal tool and an approval-required tool in the same turn.
        var normalTool = AIFunctionFactory.Create(() => "result", "NormalTool");
        var approvalTool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "result", "ApprovalTool"));

        var mockClient = new Mock<IChatClient>();
        mockClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(() => new ChatResponse(new ChatMessage(ChatRole.Assistant,
            [
                new FunctionCallContent("call1", "NormalTool"),
                new FunctionCallContent("call2", "ApprovalTool"),
            ])));

        // Disable ToolApproval so the approval requests surface in the response instead of being handled.
        var options = CreateAllDisabledOptions();
        options.ChatOptions = new ChatOptions { Tools = [normalTool, approvalTool] };

        var agent = new HarnessAgent(mockClient.Object, options);
        var session = await agent.CreateSessionAsync();

        // Act
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);

        // Assert — only the approval-required tool surfaces as an approval request; the normal tool is bypassed.
        var approvalRequests = response.Messages
            .SelectMany(m => m.Contents)
            .OfType<ToolApprovalRequestContent>()
            .ToList();
        var approvalRequest = Assert.Single(approvalRequests);
        Assert.Equal("ApprovalTool", Assert.IsType<FunctionCallContent>(approvalRequest.ToolCall).Name);
    }

    /// <summary>
    /// Verify that when bypassing is disabled, all tools (including those that do not require approval) are surfaced
    /// as approval requests, reflecting the all-or-nothing behavior of <see cref="FunctionInvokingChatClient"/>.
    /// </summary>
    [Fact]
    public async Task NonApprovalRequiredFunctionBypassing_SurfacesAllApprovalsWhenDisabledAsync()
    {
        // Arrange — the model requests both a normal tool and an approval-required tool in the same turn.
        var normalTool = AIFunctionFactory.Create(() => "result", "NormalTool");
        var approvalTool = new ApprovalRequiredAIFunction(AIFunctionFactory.Create(() => "result", "ApprovalTool"));

        var mockClient = new Mock<IChatClient>();
        mockClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(() => new ChatResponse(new ChatMessage(ChatRole.Assistant,
            [
                new FunctionCallContent("call1", "NormalTool"),
                new FunctionCallContent("call2", "ApprovalTool"),
            ])));

        var options = CreateAllDisabledOptions();
        options.DisableNonApprovalRequiredFunctionBypassing = true;
        options.ChatOptions = new ChatOptions { Tools = [normalTool, approvalTool] };

        var agent = new HarnessAgent(mockClient.Object, options);
        var session = await agent.CreateSessionAsync();

        // Act
        var response = await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);

        // Assert — both tools surface as approval requests because bypassing is disabled.
        var approvalRequests = response.Messages
            .SelectMany(m => m.Contents)
            .OfType<ToolApprovalRequestContent>()
            .Select(r => ((FunctionCallContent)r.ToolCall).Name)
            .ToList();
        Assert.Equal(2, approvalRequests.Count);
        Assert.Contains("NormalTool", approvalRequests);
        Assert.Contains("ApprovalTool", approvalRequests);
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
        var agent = new HarnessAgent(chatClient, options);

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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());

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
        var agent = new HarnessAgent(chatClient, options);

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

        var agent = new HarnessAgent(mockClient.Object, options);
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

        var agent = new HarnessAgent(mockClient.Object, CreateAllDisabledOptions());
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

        var agent = new HarnessAgent(mockClient.Object, options);
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, options);
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
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());
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
        var agent = new HarnessAgent(mockClient.Object);
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

    #region Feature: BackgroundAgentsProvider

    /// <summary>
    /// Verify that BackgroundAgentsProvider is included when BackgroundAgents are specified.
    /// </summary>
    [Fact]
    public void BackgroundAgentsProvider_IncludedWhenAgentsSpecified()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var bgAgentMock = new Mock<AIAgent>();
        bgAgentMock.Setup(a => a.Name).Returns("TestBackgroundAgent");
        var options = CreateAllDisabledOptions();
        options.BackgroundAgents = [bgAgentMock.Object];

        // Act
        var agent = new HarnessAgent(chatClient, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent?.AIContextProviders);
        Assert.Contains(innerAgent!.AIContextProviders!, p => p is BackgroundAgentsProvider);
    }

    /// <summary>
    /// Verify that BackgroundAgentsProvider is not included when BackgroundAgents is null.
    /// </summary>
    [Fact]
    public void BackgroundAgentsProvider_ExcludedWhenAgentsNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.BackgroundAgents = null;

        // Act
        var agent = new HarnessAgent(chatClient, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        if (innerAgent!.AIContextProviders != null)
        {
            Assert.DoesNotContain(innerAgent.AIContextProviders, p => p is BackgroundAgentsProvider);
        }
    }

    /// <summary>
    /// Verify that BackgroundAgentsProvider is not included when BackgroundAgents is an empty collection.
    /// </summary>
    [Fact]
    public void BackgroundAgentsProvider_ExcludedWhenAgentsEmpty()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.BackgroundAgents = Array.Empty<AIAgent>();

        // Act
        var agent = new HarnessAgent(chatClient, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        if (innerAgent!.AIContextProviders != null)
        {
            Assert.DoesNotContain(innerAgent.AIContextProviders, p => p is BackgroundAgentsProvider);
        }
    }

    /// <summary>
    /// Verify that BackgroundAgentsProviderOptions is passed through when specified.
    /// </summary>
    [Fact]
    public async Task BackgroundAgentsProvider_UsesProvidedOptionsAsync()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var bgAgentMock = new Mock<AIAgent>();
        bgAgentMock.Setup(a => a.Name).Returns("TestBackgroundAgent");
        bgAgentMock.Setup(a => a.Description).Returns("A test background agent");
        var providerOptions = new BackgroundAgentsProviderOptions
        {
            Instructions = "Custom instructions with {background_agents} list.",
        };
        var options = CreateAllDisabledOptions();
        options.BackgroundAgents = [bgAgentMock.Object];
        options.BackgroundAgentsProviderOptions = providerOptions;

        // Act
        var agent = new HarnessAgent(chatClient, options);
        var innerAgent = agent.GetService<ChatClientAgent>();
        var bgProvider = innerAgent!.AIContextProviders!.OfType<BackgroundAgentsProvider>().Single();

#pragma warning disable MAAI001
        var invokingContext = new AIContextProvider.InvokingContext(
            new Mock<AIAgent>().Object,
            new Mock<AgentSession>().Object,
            new AIContext());
#pragma warning restore MAAI001

        AIContext result = await bgProvider.InvokingAsync(invokingContext);

        // Assert — custom instructions template is used and agent info is included
        Assert.NotNull(result.Instructions);
        Assert.Contains("Custom instructions with", result.Instructions);
        Assert.Contains("TestBackgroundAgent", result.Instructions);
    }

    /// <summary>
    /// Verify that multiple background agents are all passed to the provider.
    /// </summary>
    [Fact]
    public async Task BackgroundAgentsProvider_IncludesMultipleAgentsAsync()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var agent1Mock = new Mock<AIAgent>();
        agent1Mock.Setup(a => a.Name).Returns("Agent1");
        agent1Mock.Setup(a => a.Description).Returns("First agent");
        var agent2Mock = new Mock<AIAgent>();
        agent2Mock.Setup(a => a.Name).Returns("Agent2");
        agent2Mock.Setup(a => a.Description).Returns("Second agent");
        var options = CreateAllDisabledOptions();
        options.BackgroundAgents = [agent1Mock.Object, agent2Mock.Object];

        // Act
        var agent = new HarnessAgent(chatClient, options);
        var innerAgent = agent.GetService<ChatClientAgent>();
        var bgProvider = innerAgent!.AIContextProviders!.OfType<BackgroundAgentsProvider>().Single();

#pragma warning disable MAAI001
        var invokingContext = new AIContextProvider.InvokingContext(
            new Mock<AIAgent>().Object,
            new Mock<AgentSession>().Object,
            new AIContext());
#pragma warning restore MAAI001

        AIContext result = await bgProvider.InvokingAsync(invokingContext);

        // Assert — both agents appear in the provider's instructions
        Assert.NotNull(result.Instructions);
        Assert.Contains("Agent1", result.Instructions);
        Assert.Contains("First agent", result.Instructions);
        Assert.Contains("Agent2", result.Instructions);
        Assert.Contains("Second agent", result.Instructions);
    }

    #endregion

#if NET
    #region Feature: ShellEnvironmentProvider

    /// <summary>
    /// Verify that ShellEnvironmentProvider is included when ShellExecutor is provided.
    /// </summary>
    [Fact]
    public void ShellEnvironmentProvider_IncludedWhenExecutorProvided()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var executorMock = new Mock<ShellExecutor>();
        executorMock.Setup(e => e.AsAIFunction(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<bool>()))
            .Returns(AIFunctionFactory.Create(() => "test", "run_shell"));
        var options = CreateAllDisabledOptions();
        options.ShellExecutor = executorMock.Object;

        // Act
        var agent = new HarnessAgent(chatClient, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent?.AIContextProviders);
        Assert.Contains(innerAgent!.AIContextProviders!, p => p is ShellEnvironmentProvider);
    }

    /// <summary>
    /// Verify that ShellEnvironmentProvider is not included when ShellExecutor is null.
    /// </summary>
    [Fact]
    public void ShellEnvironmentProvider_ExcludedWhenExecutorNull()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.ShellExecutor = null;

        // Act
        var agent = new HarnessAgent(chatClient, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert
        Assert.NotNull(innerAgent);
        Assert.NotNull(innerAgent!.AIContextProviders);
        Assert.DoesNotContain(innerAgent.AIContextProviders!, p => p is ShellEnvironmentProvider);
    }

    /// <summary>
    /// Verify that the shell tool AIFunction is added to ChatOptions.Tools when ShellExecutor is provided.
    /// </summary>
    [Fact]
    public async Task ShellExecutor_ToolAddedToChatOptionsAsync()
    {
        // Arrange
        ChatOptions? capturedOptions = null;
        var chatClientMock = new Mock<IChatClient>();
        chatClientMock
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "done")));

        var executorMock = new Mock<ShellExecutor>();
        executorMock.Setup(e => e.AsAIFunction(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<bool>()))
            .Returns(AIFunctionFactory.Create(() => "shell output", "run_shell"));

        var options = CreateAllDisabledOptions();
        options.DisableWebSearch = true;
        options.ShellExecutor = executorMock.Object;

        // Act
        var agent = new HarnessAgent(chatClientMock.Object, options);
        var session = await agent.CreateSessionAsync();
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);

        // Assert — the shell tool should be present
        Assert.NotNull(capturedOptions?.Tools);
        Assert.Contains(capturedOptions!.Tools!, t => t is AIFunction f && f.Name == "run_shell");
    }

    /// <summary>
    /// Verify that a custom shell tool name, description, and approval flag are forwarded to the executor.
    /// </summary>
    [Fact]
    public async Task ShellExecutor_CustomToolNameDescriptionAndApprovalForwardedAsync()
    {
        // Arrange
        ChatOptions? capturedOptions = null;
        var chatClientMock = new Mock<IChatClient>();
        chatClientMock
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "done")));

        string? capturedName = null;
        string? capturedDescription = null;
        bool? capturedRequireApproval = null;
        var executorMock = new Mock<ShellExecutor>();
        executorMock.Setup(e => e.AsAIFunction(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<bool>()))
            .Callback<string, string?, bool>((name, description, requireApproval) =>
            {
                capturedName = name;
                capturedDescription = description;
                capturedRequireApproval = requireApproval;
            })
            .Returns(AIFunctionFactory.Create(() => "shell output", "custom_shell"));

        var options = CreateAllDisabledOptions();
        options.DisableWebSearch = true;
        options.ShellExecutor = executorMock.Object;
        options.ShellToolName = "custom_shell";
        options.ShellToolDescription = "Run a custom command.";
        options.DisableShellToolApproval = true;

        // Act
        var agent = new HarnessAgent(chatClientMock.Object, options);
        var session = await agent.CreateSessionAsync();
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);

        // Assert — the configured values are passed through to the executor and the tool is registered.
        Assert.Equal("custom_shell", capturedName);
        Assert.Equal("Run a custom command.", capturedDescription);
        Assert.False(capturedRequireApproval);
        Assert.NotNull(capturedOptions?.Tools);
        Assert.Contains(capturedOptions!.Tools!, t => t is AIFunction f && f.Name == "custom_shell");
    }

    /// <summary>
    /// Verify that the shell tool defaults to requiring approval and the executor's default name when not configured.
    /// </summary>
    [Fact]
    public async Task ShellExecutor_DefaultsToApprovalAndDefaultNameAsync()
    {
        // Arrange
        var chatClientMock = new Mock<IChatClient>();
        chatClientMock
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "done")));

        bool? capturedRequireApproval = null;
        string? capturedName = null;
        var executorMock = new Mock<ShellExecutor>();
        executorMock.Setup(e => e.AsAIFunction(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<bool>()))
            .Callback<string, string?, bool>((name, _, requireApproval) =>
            {
                capturedName = name;
                capturedRequireApproval = requireApproval;
            })
            .Returns(AIFunctionFactory.Create(() => "shell output", "run_shell"));

        var options = CreateAllDisabledOptions();
        options.DisableWebSearch = true;
        options.ShellExecutor = executorMock.Object;

        // Act
        var agent = new HarnessAgent(chatClientMock.Object, options);
        var session = await agent.CreateSessionAsync();
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);

        // Assert — approval is required by default and the executor's default name is used.
        Assert.True(capturedRequireApproval);
        Assert.Equal("run_shell", capturedName);
    }

    /// <summary>
    /// Verify that disabling shell approval is honored end-to-end when the underlying executor permits unapproved use:
    /// a real <see cref="LocalShellExecutor"/> constructed with <see cref="LocalShellExecutorOptions.AcknowledgeUnsafe"/>
    /// set to <see langword="true"/> plus <see cref="HarnessAgentOptions.DisableShellToolApproval"/> set to
    /// <see langword="true"/> yields a shell tool that is not wrapped in an <see cref="ApprovalRequiredAIFunction"/>.
    /// </summary>
    [Fact]
    public async Task ShellExecutor_ApprovalDisabledWithAcknowledgedExecutorProducesNonApprovalToolAsync()
    {
        // Arrange
        ChatOptions? capturedOptions = null;
        var chatClientMock = new Mock<IChatClient>();
        chatClientMock
            .Setup(c => c.GetResponseAsync(It.IsAny<IEnumerable<ChatMessage>>(), It.IsAny<ChatOptions>(), It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions?, CancellationToken>((_, opts, _) => capturedOptions = opts)
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "done")));

        await using var executor = new LocalShellExecutor(new LocalShellExecutorOptions { AcknowledgeUnsafe = true });

        var options = CreateAllDisabledOptions();
        options.DisableWebSearch = true;
        options.ShellExecutor = executor;
        options.DisableShellToolApproval = true;

        // Act
        var agent = new HarnessAgent(chatClientMock.Object, options);
        var session = await agent.CreateSessionAsync();
        await agent.RunAsync([new ChatMessage(ChatRole.User, "Hi")], session);

        // Assert — the shell tool is registered but not gated by approval.
        Assert.NotNull(capturedOptions?.Tools);
        var shellTool = Assert.Single(capturedOptions!.Tools!, t => t is AIFunction f && f.Name == "run_shell");
        Assert.IsNotType<ApprovalRequiredAIFunction>(shellTool);
    }

    /// <summary>
    /// Verify that ShellEnvironmentProvider is present when ShellEnvironmentProviderOptions is also specified.
    /// </summary>
    [Fact]
    public void ShellEnvironmentProvider_PresentWhenOptionsProvided()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var executorMock = new Mock<ShellExecutor>();
        executorMock.Setup(e => e.AsAIFunction(It.IsAny<string>(), It.IsAny<string?>(), It.IsAny<bool>()))
            .Returns(AIFunctionFactory.Create(() => "test", "run_shell"));
        var envOptions = new ShellEnvironmentProviderOptions
        {
            ProbeTools = ["git", "python"],
        };
        var options = CreateAllDisabledOptions();
        options.ShellExecutor = executorMock.Object;
        options.ShellEnvironmentProviderOptions = envOptions;

        // Act
        var agent = new HarnessAgent(chatClient, options);
        var innerAgent = agent.GetService<ChatClientAgent>();

        // Assert — provider should exist (options wiring is validated by the provider's behavior)
        Assert.NotNull(innerAgent?.AIContextProviders);
        Assert.Contains(innerAgent!.AIContextProviders!, p => p is ShellEnvironmentProvider);
    }

    #endregion
#endif

    #region LoggerFactory and ServiceProvider

    /// <summary>
    /// Verify that the constructor succeeds when loggerFactory is provided.
    /// </summary>
    [Fact]
    public void Constructor_SucceedsWithLoggerFactory()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var loggerFactory = new Mock<ILoggerFactory>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions(), loggerFactory);

        // Assert
        Assert.NotNull(agent);
    }

    /// <summary>
    /// Verify that the constructor succeeds when serviceProvider is provided.
    /// </summary>
    [Fact]
    public void Constructor_SucceedsWithServiceProvider()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var services = new Mock<IServiceProvider>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions(), services: services);

        // Assert
        Assert.NotNull(agent);
    }

    /// <summary>
    /// Verify that the constructor succeeds when both loggerFactory and serviceProvider are provided.
    /// </summary>
    [Fact]
    public void Constructor_SucceedsWithLoggerFactoryAndServiceProvider()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var loggerFactory = new Mock<ILoggerFactory>().Object;
        var services = new Mock<IServiceProvider>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions(), loggerFactory, services);

        // Assert
        Assert.NotNull(agent);
    }

    /// <summary>
    /// Verify that AsHarnessAgent extension method accepts loggerFactory and serviceProvider.
    /// </summary>
    [Fact]
    public void AsHarnessAgent_SucceedsWithLoggerFactoryAndServiceProvider()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var loggerFactory = new Mock<ILoggerFactory>().Object;
        var services = new Mock<IServiceProvider>().Object;

        // Act
        var agent = chatClient.AsHarnessAgent(CreateAllDisabledOptions(), loggerFactory, services);

        // Assert
        Assert.NotNull(agent);
    }

    /// <summary>
    /// Verify that ILoggerFactory is threaded to downstream components by confirming CreateLogger is called.
    /// </summary>
    [Fact]
    public void Constructor_LoggerFactoryIsUsedByDownstreamComponents()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var mockLoggerFactory = new Mock<ILoggerFactory>();
        mockLoggerFactory
            .Setup(lf => lf.CreateLogger(It.IsAny<string>()))
            .Returns(new Mock<ILogger>().Object);

        // Act — use options that leave CompactionProvider and AgentSkillsProvider enabled
        var options = new HarnessAgentOptions
        {
            MaxContextWindowTokens = TestMaxContextWindowTokens,
            MaxOutputTokens = TestMaxOutputTokens,
            DisableToolAutoApproval = true,
            DisableOpenTelemetry = true,
            DisableFileMemory = true,
            DisableFileAccess = true,
            DisableWebSearch = true,
            DisableTodoProvider = true,
            DisableAgentModeProvider = true,
        };
        var agent = new HarnessAgent(chatClient, options, mockLoggerFactory.Object);

        // Assert — CreateLogger should have been called by one or more downstream components
        Assert.NotNull(agent);
        mockLoggerFactory.Verify(lf => lf.CreateLogger(It.IsAny<string>()), Times.AtLeastOnce());
    }

    /// <summary>
    /// Verify that IServiceProvider is propagated through the agent pipeline by confirming
    /// it is queried during agent construction.
    /// </summary>
    [Fact]
    public void Constructor_ServiceProviderIsQueriedDuringBuild()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var mockServices = new Mock<IServiceProvider>();
        mockServices
            .Setup(sp => sp.GetService(It.IsAny<Type>()))
            .Returns(null!);

        // Act
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions(), services: mockServices.Object);

        // Assert — the service provider should have been queried during pipeline construction
        Assert.NotNull(agent);
        mockServices.Verify(sp => sp.GetService(It.IsAny<Type>()), Times.AtLeastOnce());
    }

    #endregion

    #region Compaction Opt-in

    /// <summary>
    /// Verify that constructing without token values succeeds (compaction disabled).
    /// </summary>
    [Fact]
    public void Constructor_SucceedsWithoutTokenValues()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = new HarnessAgentOptions
        {
            DisableToolAutoApproval = true,
            DisableOpenTelemetry = true,
            DisableFileMemory = true,
            DisableFileAccess = true,
            DisableWebSearch = true,
            DisableTodoProvider = true,
            DisableAgentModeProvider = true,
            DisableAgentSkillsProvider = true,
        };

        // Act
        var agent = new HarnessAgent(chatClient, options);

        // Assert — compaction should be disabled (no chat reducer)
        var innerAgent = agent.GetService<ChatClientAgent>();
        Assert.NotNull(innerAgent);
        var historyProvider = innerAgent!.ChatHistoryProvider as InMemoryChatHistoryProvider;
        Assert.NotNull(historyProvider);
        Assert.Null(historyProvider!.ChatReducer);
    }

    /// <summary>
    /// Verify that when only MaxContextWindowTokens is provided (no MaxOutputTokens), compaction is disabled.
    /// </summary>
    [Fact]
    public void Constructor_SucceedsWithOnlyMaxContextWindowTokens()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = new HarnessAgentOptions
        {
            MaxContextWindowTokens = TestMaxContextWindowTokens,
            DisableToolAutoApproval = true,
            DisableOpenTelemetry = true,
            DisableFileMemory = true,
            DisableFileAccess = true,
            DisableWebSearch = true,
            DisableTodoProvider = true,
            DisableAgentModeProvider = true,
            DisableAgentSkillsProvider = true,
        };

        // Act
        var agent = new HarnessAgent(chatClient, options);

        // Assert — compaction should be disabled (only one token value provided)
        var innerAgent = agent.GetService<ChatClientAgent>();
        Assert.NotNull(innerAgent);
        var historyProvider = innerAgent!.ChatHistoryProvider as InMemoryChatHistoryProvider;
        Assert.NotNull(historyProvider);
        Assert.Null(historyProvider!.ChatReducer);
    }

    /// <summary>
    /// Verify that when both token values are provided, the agent is constructed successfully with compaction.
    /// </summary>
    [Fact]
    public void Constructor_SucceedsWithBothTokenValues()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());

        // Assert — compaction should be enabled (chat reducer configured)
        var innerAgent = agent.GetService<ChatClientAgent>();
        Assert.NotNull(innerAgent);
        var historyProvider = innerAgent!.ChatHistoryProvider as InMemoryChatHistoryProvider;
        Assert.NotNull(historyProvider);
        Assert.NotNull(historyProvider!.ChatReducer);
    }

    #endregion

    #region Feature: Loop

    /// <summary>
    /// Verify that no <see cref="LoopAgent"/> is added when no loop evaluators are supplied.
    /// </summary>
    [Fact]
    public void Loop_ExcludedByDefault()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;

        // Act
        var agent = new HarnessAgent(chatClient, CreateAllDisabledOptions());

        // Assert
        Assert.Null(agent.GetService<LoopAgent>());
    }

    /// <summary>
    /// Verify that an empty loop evaluator collection does not add a <see cref="LoopAgent"/>.
    /// </summary>
    [Fact]
    public void Loop_EmptyEvaluators_Excluded()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.LoopEvaluators = [];

        // Act
        var agent = new HarnessAgent(chatClient, options);

        // Assert
        Assert.Null(agent.GetService<LoopAgent>());
    }

    /// <summary>
    /// Verify that a <see cref="LoopAgent"/> is added when at least one evaluator is supplied, while the inner
    /// <see cref="ChatClientAgent"/> remains resolvable through the decorator chain.
    /// </summary>
    [Fact]
    public void Loop_IncludedWhenEvaluatorsProvided()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.LoopEvaluators = [new DelegateLoopEvaluator((_, _) => new ValueTask<LoopEvaluation>(LoopEvaluation.Stop()))];

        // Act
        var agent = new HarnessAgent(chatClient, options);

        // Assert
        Assert.NotNull(agent.GetService<LoopAgent>());
        Assert.NotNull(agent.GetService<ChatClientAgent>());
    }

    /// <summary>
    /// Verify that the <see cref="LoopAgent"/> is the outermost decorator, wrapping the <see cref="ToolApprovalAgent"/>
    /// (which is itself resolvable through the loop).
    /// </summary>
    [Fact]
    public void Loop_IsOutermost_WrappingToolApproval()
    {
        // Arrange
        var chatClient = new Mock<IChatClient>().Object;
        var options = CreateAllDisabledOptions();
        options.DisableToolAutoApproval = false;
        options.LoopEvaluators = [new DelegateLoopEvaluator((_, _) => new ValueTask<LoopEvaluation>(LoopEvaluation.Stop()))];

        // Act
        var agent = new HarnessAgent(chatClient, options);

        // Assert — the loop is the outermost decorator: it is resolvable, it wraps the tool approval agent, and
        // looking *down* from the tool approval agent does not surface the loop (proving the loop sits above it).
        Assert.NotNull(agent.GetService<LoopAgent>());
        var toolApproval = agent.GetService<ToolApprovalAgent>();
        Assert.NotNull(toolApproval);
        Assert.Null(toolApproval.GetService<LoopAgent>());
    }

    /// <summary>
    /// Verify that the loop actually drives re-invocation: an evaluator that continues once before stopping causes the
    /// inner chat client to be invoked twice.
    /// </summary>
    [Fact]
    public async Task Loop_DrivesReinvocationAsync()
    {
        // Arrange — inner client returns a response on each call.
        var mockClient = new Mock<IChatClient>();
        mockClient
            .Setup(c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse(new ChatMessage(ChatRole.Assistant, "working")));

        var options = CreateAllDisabledOptions();
        // Continue once (iteration 1), then stop on the second evaluation.
        options.LoopEvaluators = [new DelegateLoopEvaluator((ctx, _) =>
            new ValueTask<LoopEvaluation>(ctx.Iteration < 2 ? LoopEvaluation.Continue() : LoopEvaluation.Stop()))];
        var agent = new HarnessAgent(mockClient.Object, options);
        var session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync([new ChatMessage(ChatRole.User, "go")], session);

        // Assert — the inner client was invoked once per iteration (two iterations).
        mockClient.Verify(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()),
            Times.Exactly(2));
    }

    #endregion
}
