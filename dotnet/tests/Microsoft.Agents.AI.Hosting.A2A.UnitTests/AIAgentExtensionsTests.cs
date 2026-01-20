// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Microsoft.Extensions.AI;
using Moq;
using Moq.Protected;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="AIAgentExtensions"/> class.
/// </summary>
public sealed class AIAgentExtensionsTests
{
    /// <summary>
    /// Verifies that when messageSendParams.Metadata is null, the options passed to RunAsync are null.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenMetadataIsNull_PassesNullOptionsToRunAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        ITaskManager taskManager = CreateAgentMock(options => capturedOptions = options).Object.MapA2A();

        // Act
        await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] },
            Metadata = null
        });

        // Assert
        Assert.Null(capturedOptions);
    }

    /// <summary>
    /// Verifies that when messageSendParams.Metadata has values, the options.AdditionalProperties contains the converted values.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenMetadataHasValues_PassesOptionsWithAdditionalPropertiesToRunAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        ITaskManager taskManager = CreateAgentMock(options => capturedOptions = options).Object.MapA2A();

        // Act
        await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] },
            Metadata = new Dictionary<string, JsonElement>
            {
                ["key1"] = JsonSerializer.SerializeToElement("value1"),
                ["key2"] = JsonSerializer.SerializeToElement(42)
            }
        });

        // Assert
        Assert.NotNull(capturedOptions);
        Assert.NotNull(capturedOptions.AdditionalProperties);
        Assert.Equal(2, capturedOptions.AdditionalProperties.Count);
        Assert.True(capturedOptions.AdditionalProperties.ContainsKey("key1"));
        Assert.True(capturedOptions.AdditionalProperties.ContainsKey("key2"));
    }

    /// <summary>
    /// Verifies that when messageSendParams.Metadata is an empty dictionary, the options passed to RunAsync is null
    /// because the ToAdditionalProperties extension method returns null for empty dictionaries.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenMetadataIsEmptyDictionary_PassesNullOptionsToRunAsync()
    {
        // Arrange
        AgentRunOptions? capturedOptions = null;
        ITaskManager taskManager = CreateAgentMock(options => capturedOptions = options).Object.MapA2A();

        // Act
        await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] },
            Metadata = []
        });

        // Assert
        Assert.Null(capturedOptions);
    }

    /// <summary>
    /// Verifies that when the agent response has AdditionalProperties, the returned AgentMessage.Metadata contains the converted values.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenResponseHasAdditionalProperties_ReturnsAgentMessageWithMetadataAsync()
    {
        // Arrange
        AdditionalPropertiesDictionary additionalProps = new()
        {
            ["responseKey1"] = "responseValue1",
            ["responseKey2"] = 123
        };
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Test response")])
        {
            AdditionalProperties = additionalProps
        };
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        AgentMessage agentMessage = Assert.IsType<AgentMessage>(a2aResponse);
        Assert.NotNull(agentMessage.Metadata);
        Assert.Equal(2, agentMessage.Metadata.Count);
        Assert.True(agentMessage.Metadata.ContainsKey("responseKey1"));
        Assert.True(agentMessage.Metadata.ContainsKey("responseKey2"));
        Assert.Equal("responseValue1", agentMessage.Metadata["responseKey1"].GetString());
        Assert.Equal(123, agentMessage.Metadata["responseKey2"].GetInt32());
    }

    /// <summary>
    /// Verifies that when the agent response has null AdditionalProperties, the returned AgentMessage.Metadata is null.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenResponseHasNullAdditionalProperties_ReturnsAgentMessageWithNullMetadataAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Test response")])
        {
            AdditionalProperties = null
        };
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        AgentMessage agentMessage = Assert.IsType<AgentMessage>(a2aResponse);
        Assert.Null(agentMessage.Metadata);
    }

    /// <summary>
    /// Verifies that when the agent response has empty AdditionalProperties, the returned AgentMessage.Metadata is null.
    /// </summary>
    [Fact]
    public async Task MapA2A_WhenResponseHasEmptyAdditionalProperties_ReturnsAgentMessageWithNullMetadataAsync()
    {
        // Arrange
        AgentResponse response = new([new ChatMessage(ChatRole.Assistant, "Test response")])
        {
            AdditionalProperties = []
        };
        ITaskManager taskManager = CreateAgentMockWithResponse(response).Object.MapA2A();

        // Act
        A2AResponse a2aResponse = await InvokeOnMessageReceivedAsync(taskManager, new MessageSendParams
        {
            Message = new AgentMessage { MessageId = "test-id", Role = MessageRole.User, Parts = [new TextPart { Text = "Hello" }] }
        });

        // Assert
        AgentMessage agentMessage = Assert.IsType<AgentMessage>(a2aResponse);
        Assert.Null(agentMessage.Metadata);
    }

    private static Mock<AIAgent> CreateAgentMock(Action<AgentRunOptions?> optionsCallback)
    {
        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock.Setup(x => x.GetNewThreadAsync()).ReturnsAsync(new TestAgentThread());
        agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentThread?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .Callback<IEnumerable<ChatMessage>, AgentThread?, AgentRunOptions?, CancellationToken>(
                (_, _, options, _) => optionsCallback(options))
            .ReturnsAsync(new AgentResponse([new ChatMessage(ChatRole.Assistant, "Test response")]));

        return agentMock;
    }

    private static Mock<AIAgent> CreateAgentMockWithResponse(AgentResponse response)
    {
        Mock<AIAgent> agentMock = new() { CallBase = true };
        agentMock.SetupGet(x => x.Name).Returns("TestAgent");
        agentMock.Setup(x => x.GetNewThreadAsync()).ReturnsAsync(new TestAgentThread());
        agentMock
            .Protected()
            .Setup<Task<AgentResponse>>("RunCoreAsync",
                ItExpr.IsAny<IEnumerable<ChatMessage>>(),
                ItExpr.IsAny<AgentThread?>(),
                ItExpr.IsAny<AgentRunOptions?>(),
                ItExpr.IsAny<CancellationToken>())
            .ReturnsAsync(response);

        return agentMock;
    }

    private static async Task<A2AResponse> InvokeOnMessageReceivedAsync(ITaskManager taskManager, MessageSendParams messageSendParams)
    {
        Func<MessageSendParams, CancellationToken, Task<A2AResponse>>? handler = taskManager.OnMessageReceived;
        Assert.NotNull(handler);
        return await handler.Invoke(messageSendParams, CancellationToken.None);
    }

    private sealed class TestAgentThread : AgentThread;
}
