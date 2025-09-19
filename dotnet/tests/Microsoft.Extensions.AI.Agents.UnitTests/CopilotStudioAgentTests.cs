// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http;
using Microsoft.Agents.CopilotStudio.Client;
using Microsoft.Extensions.AI.Agents.CopilotStudio;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;

namespace Microsoft.Extensions.AI.Agents.UnitTests;

/// <summary>
/// Unit tests for the <see cref="CopilotStudioAgent"/> class.
/// </summary>
public class CopilotStudioAgentTests
{
    private static CopilotClient CreateTestCopilotClient()
    {
        // Create mock dependencies for CopilotClient
        var mockSettings = new Mock<ConnectionSettings>();
        var mockHttpClientFactory = new Mock<IHttpClientFactory>();
        var mockHttpClient = new Mock<HttpClient>();
        mockHttpClientFactory.Setup(f => f.CreateClient(It.IsAny<string>())).Returns(mockHttpClient.Object);

        return new CopilotClient(mockSettings.Object, mockHttpClientFactory.Object, NullLogger.Instance, "test-client");
    }

    #region GetService Method Tests

    /// <summary>
    /// Verify that GetService returns CopilotClient when requested.
    /// </summary>
    [Fact]
    public void GetService_RequestingCopilotClient_ReturnsCopilotClient()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result = agent.GetService(typeof(CopilotClient));

        // Assert
        Assert.NotNull(result);
        Assert.Same(client, result);
    }

    /// <summary>
    /// Verify that GetService returns AIAgentMetadata when requested.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentMetadata_ReturnsMetadata()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result = agent.GetService(typeof(AIAgentMetadata));

        // Assert
        Assert.NotNull(result);
        Assert.IsType<AIAgentMetadata>(result);
        var metadata = (AIAgentMetadata)result;
        Assert.Equal("copilot-studio", metadata.ProviderName);
    }

    /// <summary>
    /// Verify that GetService returns null for unknown service types.
    /// </summary>
    [Fact]
    public void GetService_RequestingUnknownServiceType_ReturnsNull()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result = agent.GetService(typeof(string));

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService with serviceKey parameter returns null for unknown service types.
    /// </summary>
    [Fact]
    public void GetService_WithServiceKey_ReturnsNull()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result = agent.GetService(typeof(string), "test-key");

        // Assert
        Assert.Null(result);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first and returns the agent itself when requesting CopilotStudioAgent type.
    /// </summary>
    [Fact]
    public void GetService_RequestingCopilotStudioAgentType_ReturnsBaseImplementation()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result = agent.GetService(typeof(CopilotStudioAgent));

        // Assert
        Assert.NotNull(result);
        Assert.Same(agent, result);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first and returns the agent itself when requesting AIAgent type.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentType_ReturnsBaseImplementation()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result = agent.GetService(typeof(AIAgent));

        // Assert
        Assert.NotNull(result);
        Assert.Same(agent, result);
    }

    /// <summary>
    /// Verify that GetService calls base.GetService() first but continues to derived logic when base returns null.
    /// </summary>
    [Fact]
    public void GetService_RequestingCopilotClientWithServiceKey_CallsBaseFirstThenDerivedLogic()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act - Request CopilotClient with a service key (base.GetService will return null due to serviceKey)
        var result = agent.GetService(typeof(CopilotClient), "some-key");

        // Assert
        Assert.NotNull(result);
        Assert.Same(client, result);
    }

    /// <summary>
    /// Verify that GetService returns consistent AIAgentMetadata across multiple calls.
    /// </summary>
    [Fact]
    public void GetService_RequestingAIAgentMetadata_ReturnsConsistentMetadata()
    {
        // Arrange
        var client = CreateTestCopilotClient();
        var agent = new CopilotStudioAgent(client, NullLoggerFactory.Instance);

        // Act
        var result1 = agent.GetService(typeof(AIAgentMetadata));
        var result2 = agent.GetService(typeof(AIAgentMetadata));

        // Assert
        Assert.NotNull(result1);
        Assert.NotNull(result2);
        Assert.Same(result1, result2); // Should return the same instance
        Assert.IsType<AIAgentMetadata>(result1);
        var metadata = (AIAgentMetadata)result1;
        Assert.Equal("copilot-studio", metadata.ProviderName);
    }

    #endregion
}
