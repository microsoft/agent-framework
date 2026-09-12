// Copyright (c) Microsoft. All rights reserved.

using Azure.Storage.Blobs;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.AzureStorage.UnitTests;

/// <summary>
/// Verifies Azure Blob Storage registration for hosted agents.
/// </summary>
public sealed class AzureBlobHostedAgentBuilderExtensionsTests
{
    [Fact]
    public void WithAzureBlobSessionStore_RegistersSingletonWithIsolation()
    {
        // Arrange
        var services = new ServiceCollection();
        IHostedAgentBuilder builder = services.AddAIAgent(
            "assistant",
            (_, key) => new ChatClientAgent(new NotInvokedChatClient(), name: key));
        BlobContainerClient containerClient = new("UseDevelopmentStorage=true", "agent-sessions");

        // Act
        builder.WithAzureBlobSessionStore(containerClient);
        using ServiceProvider serviceProvider = services.BuildServiceProvider();
        AgentSessionStore store = serviceProvider.GetRequiredKeyedService<AgentSessionStore>("assistant");

        // Assert
        ServiceDescriptor descriptor = Assert.Single(
            services,
            service =>
                service.ServiceType == typeof(AgentSessionStore) &&
                service.ServiceKey as string == "assistant");
        Assert.Equal(ServiceLifetime.Singleton, descriptor.Lifetime);
        Assert.IsType<IsolationKeyScopedAgentSessionStore>(store);
        Assert.NotNull(store.GetService<AzureBlobAgentSessionStore>());
    }

    [Fact]
    public void WithAzureBlobSessionStoreFactory_UsesAgentNameLifetimeAndIsolationOptions()
    {
        // Arrange
        var services = new ServiceCollection();
        IHostedAgentBuilder builder = services.AddAIAgent(
            "assistant",
            (_, key) => new ChatClientAgent(new NotInvokedChatClient(), name: key));
        BlobContainerClient containerClient = new("UseDevelopmentStorage=true", "agent-sessions");
        string? receivedAgentName = null;

        // Act
        builder.WithAzureBlobSessionStore(
            (_, agentName) =>
            {
                receivedAgentName = agentName;
                return containerClient;
            },
            lifetime: ServiceLifetime.Scoped,
            withIsolation: false);
        using ServiceProvider serviceProvider = services.BuildServiceProvider();
        AgentSessionStore store = serviceProvider.GetRequiredKeyedService<AgentSessionStore>("assistant");

        // Assert
        ServiceDescriptor descriptor = Assert.Single(
            services,
            service =>
                service.ServiceType == typeof(AgentSessionStore) &&
                service.ServiceKey as string == "assistant");
        Assert.Equal("assistant", receivedAgentName);
        Assert.Equal(ServiceLifetime.Scoped, descriptor.Lifetime);
        Assert.IsType<AzureBlobAgentSessionStore>(store);
    }
}
