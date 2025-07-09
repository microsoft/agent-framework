// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.Runtime.Abstractions.Tests;

public class AgentProxyTests
{
    private readonly Mock<IAgentRuntime> _mockRuntime;
    private readonly AgentId _agentId;
    private readonly AgentProxy _agentProxy;

    public AgentProxyTests()
    {
        this._mockRuntime = new Mock<IAgentRuntime>();
        this._agentId = new AgentId("testType", "testKey");
        this._agentProxy = new AgentProxy(this._agentId, this._mockRuntime.Object);
    }

    [Fact]
    public void IdMatchesAgentIdTest()
    {
        // Assert
        Assert.Equal(this._agentId, this._agentProxy.Id);
    }

    [Fact]
    public void MetadataShouldMatchAgentTest()
    {
        AgentMetadata expectedMetadata = new("testType", "testKey", "testDescription");
        this._mockRuntime.Setup(r => r.GetAgentMetadataAsync(this._agentId))
            .ReturnsAsync(expectedMetadata);

        Assert.Equal(expectedMetadata, this._agentProxy.Metadata);
    }

    [Fact]
    public async Task SendMessageResponseTestAsync()
    {
        // Arrange
        object message = new { Content = "Hello" };
        AgentId sender = new("senderType", "senderKey");
        object response = new { Content = "Response" };

        this._mockRuntime.Setup(r => r.SendMessageAsync(message, this._agentId, sender, null, It.IsAny<CancellationToken>()))
            .ReturnsAsync(response);

        // Act
        object? result = await this._agentProxy.SendMessageAsync(message, sender);

        // Assert
        Assert.Equal(response, result);
    }

    [Fact]
    public async Task LoadStateTestAsync()
    {
        // Arrange
        JsonElement state = JsonDocument.Parse("{\"key\":\"value\"}").RootElement;

        this._mockRuntime.Setup(r => r.LoadAgentStateAsync(this._agentId, state))
            .Returns(default(ValueTask));

        // Act
        await this._agentProxy.LoadStateAsync(state);

        // Assert
        this._mockRuntime.Verify(r => r.LoadAgentStateAsync(this._agentId, state), Times.Once);
    }

    [Fact]
    public async Task SaveStateTestAsync()
    {
        // Arrange
        JsonElement expectedState = JsonDocument.Parse("{\"key\":\"value\"}").RootElement;

        this._mockRuntime.Setup(r => r.SaveAgentStateAsync(this._agentId))
            .ReturnsAsync(expectedState);

        // Act
        JsonElement result = await this._agentProxy.SaveStateAsync();

        // Assert
        Assert.Equal(expectedState, result);
    }
}
