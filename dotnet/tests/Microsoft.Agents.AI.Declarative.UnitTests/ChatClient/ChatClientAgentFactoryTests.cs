// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.PowerFx.Types;
using Moq;

namespace Microsoft.Agents.AI.Declarative.UnitTests.ChatClient;

/// <summary>
/// Unit tests for <see cref="ChatClientPromptAgentFactory"/>.
/// </summary>
public sealed class ChatClientAgentFactoryTests
{
    private readonly Mock<IChatClient> _mockChatClient;

    public ChatClientAgentFactoryTests()
    {
        this._mockChatClient = new();
    }

    [Fact]
    public async Task TryCreateAsync_WithChatClientInConstructor_CreatesAgentAsync()
    {
        // Arrange
        var promptAgent = PromptAgents.CreateTestPromptAgent();
        ChatClientPromptAgentFactory factory = new(this._mockChatClient.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        Assert.Equal("Test Agent", agent.Name);
        Assert.Equal("Test Description", agent.Description);
    }

    [Fact]
    public async Task TryCreateAsync_Creates_ChatClientAgentAsync()
    {
        // Arrange
        var promptAgent = PromptAgents.CreateTestPromptAgent();
        ChatClientPromptAgentFactory factory = new(this._mockChatClient.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var chatClientAgent = agent as ChatClientAgent;
        Assert.NotNull(chatClientAgent);
        Assert.Equal("You are a helpful assistant.", chatClientAgent.Instructions);
        Assert.NotNull(chatClientAgent.ChatClient);
        Assert.NotNull(chatClientAgent.ChatOptions);
    }

    [Fact]
    public async Task TryCreateAsync_Creates_ChatOptionsAsync()
    {
        // Arrange
        var promptAgent = PromptAgents.CreateTestPromptAgent();
        ChatClientPromptAgentFactory factory = new(this._mockChatClient.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var chatClientAgent = agent as ChatClientAgent;
        Assert.NotNull(chatClientAgent?.ChatOptions);
        Assert.Equal("You are a helpful assistant.", chatClientAgent?.ChatOptions?.Instructions);
        Assert.Equal(0.7F, chatClientAgent?.ChatOptions?.Temperature);
        Assert.Equal(0.7F, chatClientAgent?.ChatOptions?.FrequencyPenalty);
        Assert.Equal(1024, chatClientAgent?.ChatOptions?.MaxOutputTokens);
        Assert.Equal(0.9F, chatClientAgent?.ChatOptions?.TopP);
        Assert.Equal(50, chatClientAgent?.ChatOptions?.TopK);
        Assert.Equal(0.7F, chatClientAgent?.ChatOptions?.PresencePenalty);
        Assert.Equal(42L, chatClientAgent?.ChatOptions?.Seed);
        Assert.NotNull(chatClientAgent?.ChatOptions?.ResponseFormat);
        Assert.Equal("gpt-4o", chatClientAgent?.ChatOptions?.ModelId);
        Assert.Equal(["###", "END", "STOP"], chatClientAgent?.ChatOptions?.StopSequences);
        Assert.True(chatClientAgent?.ChatOptions?.AllowMultipleToolCalls);
        Assert.Equal(ChatToolMode.Auto, chatClientAgent?.ChatOptions?.ToolMode);
        Assert.Equal("customValue", chatClientAgent?.ChatOptions?.AdditionalProperties?["customProperty"]);
    }

    [Fact]
    public async Task TryCreateAsync_Creates_ToolsAsync()
    {
        // Arrange
        var promptAgent = PromptAgents.CreateTestPromptAgent();
        ChatClientPromptAgentFactory factory = new(this._mockChatClient.Object);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.NotNull(agent);
        Assert.IsType<ChatClientAgent>(agent);
        var chatClientAgent = agent as ChatClientAgent;
        Assert.NotNull(chatClientAgent?.ChatOptions?.Tools);
        var tools = chatClientAgent?.ChatOptions?.Tools;
        Assert.Equal(5, tools?.Count);
    }

    [Fact]
    public async Task Constructor_WithNullFunctions_CreatesAgentAsync()
    {
        // Arrange
        var promptAgent = PromptAgents.CreateTestPromptAgent();
        ChatClientPromptAgentFactory factory = new(this._mockChatClient.Object, null);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent);

        // Assert
        Assert.NotNull(agent);
    }

    [Fact]
    public async Task TryCreateAsync_WithOptions_LoadsAllowedConfigurationAsync()
    {
        // Arrange
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Temperature"] = "0.9",
                ["TopP"] = "0.8",
                ["OpenAIEndpoint"] = "https://example.openai.azure.com/",
                ["OpenAIApiKey"] = "test-key",
            })
            .Build();
        GptComponentMetadata promptAgent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithVariableReferences);
        ChatClientPromptAgentFactory factory = ChatClientPromptAgentFactory.Create(
            this._mockChatClient.Object,
            options: new ChatClientPromptAgentFactoryOptions()
            {
                Configuration = configuration,
                AllowedConfigurationVariables = ["Temperature", "TopP", "OpenAIEndpoint", "OpenAIApiKey"],
            });

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent);

        // Assert
        ChatClientAgent chatClientAgent = Assert.IsType<ChatClientAgent>(agent);
        Assert.Equal(0.9F, chatClientAgent.ChatOptions?.Temperature);
        Assert.Equal(0.8F, chatClientAgent.ChatOptions?.TopP);
    }

    [Fact]
    public async Task TryCreateAsync_WithLegacyConfiguration_LoadsReferencedConfigurationAsync()
    {
        // Arrange
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Temperature"] = "0.9",
                ["TopP"] = "0.8",
                ["OpenAIEndpoint"] = "https://example.openai.azure.com/",
                ["OpenAIApiKey"] = "test-key",
            })
            .Build();
        GptComponentMetadata promptAgent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithVariableReferences);
        ChatClientPromptAgentFactory factory = new(this._mockChatClient.Object, configuration: configuration);

        // Act
        AIAgent? agent = await factory.TryCreateAsync(promptAgent);

        // Assert
        ChatClientAgent chatClientAgent = Assert.IsType<ChatClientAgent>(agent);
        Assert.Equal(0.9F, chatClientAgent.ChatOptions?.Temperature);
        Assert.Equal(0.8F, chatClientAgent.ChatOptions?.TopP);
    }

    [Fact]
    public async Task TryCreateAsync_OnlyLoadsAllowedReferencedConfigurationAsync()
    {
        // Arrange
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Temperature"] = "0.9",
                ["SOME_SECRET"] = "secret-value",
            })
            .Build();
        GptComponentMetadata promptAgent = AgentBotElementYaml.FromYaml(PromptAgents.AgentWithVariableReferences);
        InspectingPromptAgentFactory factory = new(configuration, ["Temperature"]);

        // Act
        await factory.TryCreateAsync(promptAgent);

        // Assert
        StringValue temperature = Assert.IsType<StringValue>(factory.Evaluate("Temperature"));
        Assert.Equal("0.9", temperature.Value);
        Assert.False(factory.CanEvaluate("SOME_SECRET"));
    }

    private sealed class InspectingPromptAgentFactory(IConfiguration configuration, IEnumerable<string> allowedConfigurationVariables)
        : PromptAgentFactory(engine: null, configuration: configuration, allowedConfigurationVariables: allowedConfigurationVariables)
    {
        public FormulaValue Evaluate(string expression) => this.Engine.Eval(expression);

        public bool CanEvaluate(string expression) => this.Engine.Check(expression).IsSuccess;

        public override Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
        {
            // Arrange
            this.InitializeConfigurationVariables(promptAgent);

            // Act & Assert
            return Task.FromResult<AIAgent?>(null);
        }
    }
}
