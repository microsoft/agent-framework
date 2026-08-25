// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading.Tasks;
using Microsoft.Agents.AI.CopilotStudio;
using Microsoft.Agents.CopilotStudio.Client;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Agents.AI.UnitTests.CopilotStudio;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class FeatureUsageActivationTests : IDisposable
{
    public FeatureUsageActivationTests() => FeatureUsageAssert.Reset();

    [Fact]
    public async Task RunAsync_WhenClientFails_ActivatesCopilotStudioAsync()
    {
        // Arrange
        var agent = new CopilotStudioAgent(CreateTestCopilotClient(), NullLoggerFactory.Instance);
        AgentSession session = await agent.CreateSessionAsync("conversation-id");

        // Act
        _ = await Assert.ThrowsAnyAsync<Exception>(() => agent.RunAsync("hello", session));

        // Assert
        FeatureUsageAssert.Marked(56);
    }

    [Fact]
    public async Task RunStreamingAsync_IsColdAndActivatesCopilotStudioAsync()
    {
        // Arrange
        var agent = new CopilotStudioAgent(CreateTestCopilotClient(), NullLoggerFactory.Instance);
        AgentSession session = await agent.CreateSessionAsync("conversation-id");

        // Act
        IAsyncEnumerable<AgentResponseUpdate> stream = agent.RunStreamingAsync("hello", session);

        // Assert
        Assert.Equal(string.Empty, FeatureUsage.ApplyToUserAgent(string.Empty));
        await using IAsyncEnumerator<AgentResponseUpdate> enumerator = stream.GetAsyncEnumerator();
        _ = await Assert.ThrowsAnyAsync<Exception>(async () => await enumerator.MoveNextAsync());
        FeatureUsageAssert.Marked(56);
    }

    public void Dispose() => FeatureUsageAssert.Reset();

    private static CopilotClient CreateTestCopilotClient()
    {
        Mock<ConnectionSettings> settings = new();
        Mock<IHttpClientFactory> httpClientFactory = new();
        httpClientFactory
            .Setup(factory => factory.CreateClient(It.IsAny<string>()))
            .Returns(new Mock<HttpClient>().Object);

        return new CopilotClient(
            settings.Object,
            httpClientFactory.Object,
            NullLogger.Instance,
            "test-client");
    }
}
