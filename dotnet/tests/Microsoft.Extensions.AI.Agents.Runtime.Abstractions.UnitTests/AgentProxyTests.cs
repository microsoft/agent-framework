// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Moq;

namespace Microsoft.Extensions.AI.Agents.Runtime.Abstractions.Tests;

public class AgentProxyTests
{
    private readonly Mock<IAgentRuntime> _mockRuntime;
    private readonly ActorId _agentId;
    private readonly IdProxyActor _agentProxy;

    public AgentProxyTests()
    {
        this._mockRuntime = new Mock<IAgentRuntime>();
        this._agentId = new ActorId("testType", "testKey");
        this._agentProxy = new IdProxyActor(this._mockRuntime.Object, this._agentId);
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
        ActorMetadata expectedMetadata = new(new("testType"), "testKey", "testDescription");
        this._mockRuntime.Setup(r => r.GetActorMetadataAsync(this._agentId, default))
            .ReturnsAsync(expectedMetadata);

        Assert.Equal(expectedMetadata, this._agentProxy.Metadata);
    }

    [Fact]
    public async Task SendMessageResponseTestAsync()
    {
        // Arrange
        object message = new { Content = "Hello" };
        ActorId sender = new("senderType", "senderKey");
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

        this._mockRuntime.Setup(r => r.LoadActorStateAsync(this._agentId, state, default))
            .Returns(default(ValueTask));

        // Act
        await this._agentProxy.LoadStateAsync(state);

        // Assert
        this._mockRuntime.Verify(r => r.LoadActorStateAsync(this._agentId, state, default), Times.Once);
    }

    [Fact]
    public async Task SaveStateTestAsync()
    {
        // Arrange
        JsonElement expectedState = JsonDocument.Parse("{\"key\":\"value\"}").RootElement;

        this._mockRuntime.Setup(r => r.SaveActorStateAsync(this._agentId, default))
            .ReturnsAsync(expectedState);

        // Act
        JsonElement result = await this._agentProxy.SaveStateAsync();

        // Assert
        Assert.Equal(expectedState, result);
    }
}
