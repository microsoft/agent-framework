// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.UnitTests;

/// <summary>
/// Contains unit tests for the ChatClientExtensions class.
/// </summary>
public sealed class ChatClientExtensionsTests
{
    [Fact]
    public void CreateAIAgent_WithBasicParameters_CreatesAgent()
    {
        // Arrange
        var chatClientMock = new Mock<IChatClient>();

        // Act
        var agent = chatClientMock.Object.AsAIAgent(
            instructions: "Test instructions",
            name: "TestAgent",
            description: "Test description"
        );

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("TestAgent", agent.Name);
        Assert.Equal("Test description", agent.Description);
        Assert.Equal("Test instructions", agent.Instructions);
    }

    [Fact]
    public void CreateAIAgent_WithTools_SetsToolsInOptions()
    {
        // Arrange
        var chatClientMock = new Mock<IChatClient>();
        var tools = new List<AITool> { new Mock<AITool>().Object };

        // Act
        var agent = chatClientMock.Object.AsAIAgent(tools: tools);

        // Assert
        Assert.NotNull(agent);
        Assert.NotNull(agent.ChatOptions);
        Assert.Equal(tools, agent.ChatOptions.Tools);
    }

    [Fact]
    public void CreateAIAgent_WithOptions_CreatesAgentWithOptions()
    {
        // Arrange
        var chatClientMock = new Mock<IChatClient>();
        var options = new ChatClientAgentOptions
        {
            Name = "AgentWithOptions",
            Description = "Desc",
            ChatOptions = new() { Instructions = "Instr" },
            UseProvidedChatClientAsIs = true
        };

        // Act
        var agent = chatClientMock.Object.AsAIAgent(options);

        // Assert
        Assert.NotNull(agent);
        Assert.Equal("AgentWithOptions", agent.Name);
        Assert.Equal("Desc", agent.Description);
        Assert.Equal("Instr", agent.Instructions);
        Assert.Same(chatClientMock.Object, agent.ChatClient);
    }

    [Fact]
    public void CreateAIAgent_WithConcurrentInvocation_EnablesConcurrentFunctionInvocation()
    {
        // Arrange
        var chatClientMock = new Mock<IChatClient>();
        var options = new ChatClientAgentOptions { AllowConcurrentInvocation = true };

        // Act
        var agent = chatClientMock.Object.AsAIAgent(options);

        // Assert
        var functionInvokingClient = agent.ChatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.True(functionInvokingClient.AllowConcurrentInvocation);
    }

    [Theory]
    [InlineData(false, true)]
    [InlineData(true, false)]
    public void CreateAIAgent_WithExistingFunctionInvokingChatClient_ConfiguresConcurrentInvocation(bool initiallyEnabled, bool allowConcurrentInvocation)
    {
        // Arrange
        var chatClientMock = new Mock<IChatClient>();
        var chatClient = chatClientMock.Object.AsBuilder()
            .UseFunctionInvocation(configure: client => client.AllowConcurrentInvocation = initiallyEnabled)
            .Build();
        var options = new ChatClientAgentOptions { AllowConcurrentInvocation = allowConcurrentInvocation };

        // Act
        var agent = chatClient.AsAIAgent(options);

        // Assert
        var functionInvokingClient = agent.ChatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.True(functionInvokingClient.AllowConcurrentInvocation);
    }

    [Fact]
    public void CreateAIAgent_SharedChatClient_DoesNotLeakToolsBetweenAgents()
    {
        // Arrange: a single pre-decorated IChatClient shared by two independently-constructed agents,
        // one "privileged" and one "public", each with their own distinct tool.
        var chatClientMock = new Mock<IChatClient>();
        var sharedChatClient = chatClientMock.Object.AsBuilder().UseFunctionInvocation().Build();

        AITool publicTool = AIFunctionFactory.Create(() => "public", name: "public_read");
        AITool privilegedTool = AIFunctionFactory.Create(() => "privileged", name: "privileged_write");

        // Act: construct the low-privilege agent first, then the privileged agent on the same shared client.
        var publicAgent = sharedChatClient.AsAIAgent(tools: [publicTool]);
        var privilegedAgent = sharedChatClient.AsAIAgent(tools: [privilegedTool]);

        // Assert: neither agent mutated the shared FunctionInvokingChatClient's AdditionalTools, so
        // constructing the privileged agent cannot overwrite/leak tools into the public agent's execution scope.
        var functionInvokingClient = sharedChatClient.GetService<FunctionInvokingChatClient>();
        Assert.NotNull(functionInvokingClient);
        Assert.True(functionInvokingClient.AdditionalTools is null or { Count: 0 });

        // Each agent's own configured tools remain scoped to itself.
        Assert.Equal([publicTool], publicAgent.ChatOptions!.Tools);
        Assert.Equal([privilegedTool], privilegedAgent.ChatOptions!.Tools);
    }

    [Fact]
    public void CreateAIAgent_WithNullClient_Throws()
    {
        // Arrange
        IChatClient chatClient = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => chatClient.AsAIAgent(instructions: "instructions"));
    }

    [Fact]
    public void CreateAIAgent_WithNullClientAndOptions_Throws()
    {
        // Arrange
        IChatClient chatClient = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => chatClient.AsAIAgent(options: new() { ChatOptions = new() { Instructions = "instructions" } }));
    }
}
