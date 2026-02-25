// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Agents.AI.Agentforce;

namespace Microsoft.Agents.AI.Agentforce.UnitTests;

public class AgentforceClientTests
{
    [Fact]
    public void Constructor_WithNullConfig_Throws()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new AgentforceClient(null!));
    }

    [Fact]
    public void Constructor_WithValidConfig_CreatesClient()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");

        // Act
        using var client = new AgentforceClient(config);

        // Assert - no exception thrown, client created successfully.
        Assert.NotNull(client);
    }

    [Fact]
    public void Constructor_WithExternalHttpClient_UsesIt()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        using var httpClient = new System.Net.Http.HttpClient();

        // Act
        using var client = new AgentforceClient(config, httpClient);

        // Assert
        Assert.NotNull(client);
    }

    [Fact]
    public void Dispose_CalledTwice_DoesNotThrow()
    {
        // Arrange
        var config = new AgentforceConfig("test.salesforce.com", "key", "secret", "agent-id");
        var client = new AgentforceClient(config);

        // Act & Assert
        client.Dispose();
        client.Dispose(); // Should not throw.
    }
}
