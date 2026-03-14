// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains tests for <see cref="ChatOptions"/> merging in <see cref="ChatClientAgent"/>.
/// </summary>
public class ChatClientAgent_ChatOptionsMergingTests
{
    /// <summary>
    /// Verify that ChatOptions merging works when agent has ChatOptions but request doesn't.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingUsesAgentOptionsWhenRequestHasNoneAsync()
    {
        // Arrange
        var agentChatOptions = new ChatOptions { MaxOutputTokens = 100, Temperature = 0.7f, Instructions = "test instructions" };
        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equal(100, capturedChatOptions.MaxOutputTokens);
        Assert.Equal(0.7f, capturedChatOptions.Temperature);
        Assert.Equal("test instructions", capturedChatOptions.Instructions);
    }

    [Fact]
    public async Task ChatOptionsMergingUsesAgentOptionsConstructorWhenRequestHasNoneAsync()
    {
        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
                s => s.GetResponseAsync(
                    It.IsAny<IEnumerable<ChatMessage>>(),
                    It.IsAny<ChatOptions>(),
                    It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new() { ChatOptions = new() { Instructions = "test instructions" } });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages);

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equal("test instructions", capturedChatOptions.Instructions);
    }

    /// <summary>
    /// Verify that ChatOptions merging works when request has ChatOptions but agent doesn't.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingUsesRequestOptionsWhenAgentHasNoneAsync()
    {
        // Arrange
        var requestChatOptions = new ChatOptions { MaxOutputTokens = 200, Temperature = 0.3f, Instructions = "test instructions" };
        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, options: new ChatClientAgentRunOptions(requestChatOptions));

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equivalent(requestChatOptions, capturedChatOptions); // Should be the same instance since no merging needed
        Assert.Equal(200, capturedChatOptions.MaxOutputTokens);
        Assert.Equal(0.3f, capturedChatOptions.Temperature);
        Assert.Equal("test instructions", capturedChatOptions.Instructions);
    }

    /// <summary>
    /// Verify that <see cref="ChatOptions"/> merging prioritizes <see cref="AgentRunOptions"/> over request <see cref="ChatOptions"/> and that in turn over agent level <see cref="ChatOptions"/>.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingPrioritizesRequestOptionsOverAgentOptionsAsync()
    {
        // Arrange
        var agentChatOptions = new ChatOptions
        {
            Instructions = "test instructions",
            MaxOutputTokens = 100,
            Temperature = 0.7f,
            TopP = 0.9f,
            ModelId = "agent-model",
            AdditionalProperties = new AdditionalPropertiesDictionary { ["key1"] = "agent-value", ["key2"] = "agent-value", ["key3"] = "agent-value" }
        };
        var requestChatOptions = new ChatOptions
        {
            // TopP and ModelId not set, should use agent values
            MaxOutputTokens = 200,
            Temperature = 0.3f,
            AdditionalProperties = new AdditionalPropertiesDictionary { ["key2"] = "request-value", ["key3"] = "request-value" },
            Instructions = "request instructions"
        };
        var agentRunOptionsAdditionalProperties = new AdditionalPropertiesDictionary { ["key3"] = "runoptions-value" };
        var expectedChatOptionsMerge = new ChatOptions
        {
            MaxOutputTokens = 200, // Request value takes priority
            Temperature = 0.3f, // Request value takes priority
            // Check that each level of precedence is respected in AdditionalProperties
            AdditionalProperties = new AdditionalPropertiesDictionary { ["key1"] = "agent-value", ["key2"] = "request-value", ["key3"] = "runoptions-value" },
            TopP = 0.9f, // Agent value used when request doesn't specify
            ModelId = "agent-model", // Agent value used when request doesn't specify
            Instructions = "test instructions\nrequest instructions" // Request is in addition to agent instructions
        };

        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, options: new ChatClientAgentRunOptions(requestChatOptions) { AdditionalProperties = agentRunOptionsAdditionalProperties });

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equivalent(expectedChatOptionsMerge, capturedChatOptions); // Should be the same instance (modified in place)
        Assert.Equal(200, capturedChatOptions.MaxOutputTokens); // Request value takes priority
        Assert.Equal(0.3f, capturedChatOptions.Temperature); // Request value takes priority
        Assert.NotNull(capturedChatOptions.AdditionalProperties);
        Assert.Equal("agent-value", capturedChatOptions.AdditionalProperties["key1"]); // Agent value used when request doesn't specify
        Assert.Equal("request-value", capturedChatOptions.AdditionalProperties["key2"]); // Request ChatOptions value takes priority over agent ChatOptions value
        Assert.Equal("runoptions-value", capturedChatOptions.AdditionalProperties["key3"]); // Run options value takes priority over request and agent ChatOptions values
        Assert.Equal(0.9f, capturedChatOptions.TopP); // Agent value used when request doesn't specify
        Assert.Equal("agent-model", capturedChatOptions.ModelId); // Agent value used when request doesn't specify
    }

    /// <summary>
    /// Verify that ChatOptions merging returns null when both agent and request have no ChatOptions.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingReturnsNullWhenBothAgentAndRequestHaveNoneAsync()
    {
        // Arrange
        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object);
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages);

        // Assert
        Assert.Null(capturedChatOptions);
    }

    /// <summary>
    /// Verify that ChatOptions merging concatenates Tools from agent and request.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingConcatenatesToolsFromAgentAndRequestAsync()
    {
        // Arrange
        var agentTool = AIFunctionFactory.Create(() => "agent tool");
        var requestTool = AIFunctionFactory.Create(() => "request tool");

        var agentChatOptions = new ChatOptions
        {
            Instructions = "test instructions",
            Tools = [agentTool]
        };
        var requestChatOptions = new ChatOptions
        {
            Tools = [requestTool]
        };

        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, options: new ChatClientAgentRunOptions(requestChatOptions));

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.NotNull(capturedChatOptions.Tools);
        Assert.Equal(2, capturedChatOptions.Tools.Count);

        // Request tools should come first, then agent tools
        Assert.Contains(requestTool, capturedChatOptions.Tools);
        Assert.Contains(agentTool, capturedChatOptions.Tools);
    }

    /// <summary>
    /// Verify that ChatOptions merging uses agent Tools when request has no Tools.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingUsesAgentToolsWhenRequestHasNoToolsAsync()
    {
        // Arrange
        var agentTool = AIFunctionFactory.Create(() => "agent tool");

        var agentChatOptions = new ChatOptions
        {
            Instructions = "test instructions",
            Tools = [agentTool]
        };
        var requestChatOptions = new ChatOptions
        {
            // No Tools specified
            MaxOutputTokens = 100
        };

        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, options: new ChatClientAgentRunOptions(requestChatOptions));

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.NotNull(capturedChatOptions.Tools);
        Assert.Single(capturedChatOptions.Tools);
        Assert.Contains(agentTool, capturedChatOptions.Tools); // Should contain the agent's tool
    }

    /// <summary>
    /// Verify that ChatOptions merging uses RawRepresentationFactory from request first, with fallback to agent.
    /// </summary>
    [Theory]
    [InlineData("MockAgentSetting", "MockRequestSetting", "MockRequestSetting")]
    [InlineData("MockAgentSetting", null, "MockAgentSetting")]
    [InlineData(null, "MockRequestSetting", "MockRequestSetting")]
    public async Task ChatOptionsMergingUsesRawRepresentationFactoryWithFallbackAsync(string? agentSetting, string? requestSetting, string expectedSetting)
    {
        // Arrange
        var agentChatOptions = new ChatOptions
        {
            Instructions = "test instructions",
            RawRepresentationFactory = _ => agentSetting
        };
        var requestChatOptions = new ChatOptions
        {
            RawRepresentationFactory = _ => requestSetting
        };

        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, options: new ChatClientAgentRunOptions(requestChatOptions));

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.NotNull(capturedChatOptions.RawRepresentationFactory);
        Assert.Equal(expectedSetting, capturedChatOptions.RawRepresentationFactory(null!));
    }

    /// <summary>
    /// Verify that ChatOptions merging handles all scalar properties correctly.
    /// </summary>
    [Fact]
    public async Task ChatOptionsMergingHandlesAllScalarPropertiesCorrectlyAsync()
    {
        // Arrange
        var agentChatOptions = new ChatOptions
        {
            MaxOutputTokens = 100,
            Temperature = 0.7f,
            TopP = 0.9f,
            TopK = 50,
            PresencePenalty = 0.1f,
            FrequencyPenalty = 0.2f,
            Instructions = "agent instructions",
            ModelId = "agent-model",
            Seed = 12345,
            ConversationId = "agent-conversation",
            AllowMultipleToolCalls = true,
            StopSequences = ["agent-stop"]
        };
        var requestChatOptions = new ChatOptions
        {
            MaxOutputTokens = 200,
            Temperature = 0.3f,
            Instructions = "request instructions",

            // Other properties not set, should use agent values
            StopSequences = ["request-stop"]
        };

        var expectedChatOptionsMerge = new ChatOptions
        {
            MaxOutputTokens = 200,
            Temperature = 0.3f,

            // Agent value used when request doesn't specify
            TopP = 0.9f,
            TopK = 50,
            PresencePenalty = 0.1f,
            FrequencyPenalty = 0.2f,
            Instructions = "agent instructions\nrequest instructions",
            ModelId = "agent-model",
            Seed = 12345,
            ConversationId = "agent-conversation",
            AllowMultipleToolCalls = true,

            // Merged StopSequences
            StopSequences = ["request-stop", "agent-stop"]
        };

        Mock<IChatClient> mockService = new();
        ChatOptions? capturedChatOptions = null;
        mockService.Setup(
            s => s.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .Callback<IEnumerable<ChatMessage>, ChatOptions, CancellationToken>((msgs, opts, ct) =>
                capturedChatOptions = opts)
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, "response")]));

        ChatClientAgent agent = new(mockService.Object, options: new()
        {
            ChatOptions = agentChatOptions
        });
        var messages = new List<ChatMessage> { new(ChatRole.User, "test") };

        // Act
        await agent.RunAsync(messages, options: new ChatClientAgentRunOptions(requestChatOptions));

        // Assert
        Assert.NotNull(capturedChatOptions);
        Assert.Equivalent(expectedChatOptionsMerge, capturedChatOptions); // Should be the equivalent instance (modified in place)

        // Request values should take priority
        Assert.Equal(200, capturedChatOptions.MaxOutputTokens);
        Assert.Equal(0.3f, capturedChatOptions.Temperature);

        // Merge StopSequences
        Assert.Equal(["request-stop", "agent-stop"], capturedChatOptions.StopSequences);

        // Agent values should be used when request doesn't specify
        Assert.Equal(0.9f, capturedChatOptions.TopP);
        Assert.Equal(50, capturedChatOptions.TopK);
        Assert.Equal(0.1f, capturedChatOptions.PresencePenalty);
        Assert.Equal(0.2f, capturedChatOptions.FrequencyPenalty);
        Assert.Equal("agent-model", capturedChatOptions.ModelId);
        Assert.Equal(12345, capturedChatOptions.Seed);
        Assert.Equal("agent-conversation", capturedChatOptions.ConversationId);
        Assert.Equal(true, capturedChatOptions.AllowMultipleToolCalls);
    }
}
