// Copyright (c) Microsoft. All rights reserved.

using System;
using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Tests for <see cref="HostedFoundryMemoryProviderServiceCollectionExtensions"/>.
/// </summary>
public class HostedFoundryMemoryProviderServiceCollectionExtensionsTests
{
    private const string TestUserId = "ext-user-1";
    private const string MemoryStoreName = "test-memory-store";

    [Fact]
    public void AddHostedFoundryMemoryProvider_ExplicitClient_RegistersSingleton()
    {
        // Arrange
        var services = new ServiceCollection();
        var client = CreateClient();

        // Act
        services.AddHostedFoundryMemoryProvider(client, MemoryStoreName);
        var sp = services.BuildServiceProvider();

        // Assert
        var first = sp.GetRequiredService<FoundryMemoryProvider>();
        var second = sp.GetRequiredService<FoundryMemoryProvider>();
        Assert.Same(first, second);
    }

    [Fact]
    public void AddHostedFoundryMemoryProvider_DiResolvedClient_RegistersSingleton()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddSingleton(CreateClient());

        // Act
        services.AddHostedFoundryMemoryProvider(MemoryStoreName);
        var sp = services.BuildServiceProvider();

        // Assert
        var first = sp.GetRequiredService<FoundryMemoryProvider>();
        var second = sp.GetRequiredService<FoundryMemoryProvider>();
        Assert.Same(first, second);
    }

    [Fact]
    public void AddHostedFoundryMemoryProvider_DiResolvedClient_MissingClient_Throws()
    {
        // Arrange
        var services = new ServiceCollection();

        // Act
        services.AddHostedFoundryMemoryProvider(MemoryStoreName);
        var sp = services.BuildServiceProvider();

        // Assert
        Assert.Throws<InvalidOperationException>(() => sp.GetRequiredService<FoundryMemoryProvider>());
    }

    [Fact]
    public void AddHostedFoundryMemoryProvider_NullStateInitializer_DefaultsToPerUser()
    {
        // Arrange
        var session = CreateTaggedSession();

        // Act
        var services = new ServiceCollection();
        services.AddHostedFoundryMemoryProvider(CreateClient(), MemoryStoreName);
        var provider = services.BuildServiceProvider().GetRequiredService<FoundryMemoryProvider>();

        // Assert
        Assert.NotNull(provider);
        var defaultInitializer = HostedFoundryMemoryProviderScopes.PerUser();
        var state = defaultInitializer(session);
        Assert.Equal(TestUserId, state.Scope.Scope);
    }

    [Fact]
    public void AddHostedFoundryMemoryProvider_CustomStateInitializer_IsHonored()
    {
        // Arrange
        var session = CreateTaggedSession();
        static FoundryMemoryProvider.State Custom(AgentSession? _)
            => new(new FoundryMemoryProviderScope("custom-scope"));

        // Act
        var services = new ServiceCollection();
        services.AddHostedFoundryMemoryProvider(CreateClient(), MemoryStoreName, Custom);
        var provider = services.BuildServiceProvider().GetRequiredService<FoundryMemoryProvider>();

        // Assert
        Assert.NotNull(provider);
        var state = Custom(session);
        Assert.Equal("custom-scope", state.Scope.Scope);
    }

    private static AIProjectClient CreateClient()
        => new(new Uri("https://example.services.ai.azure.com/api/projects/test"), new DefaultAzureCredential());

    private static BareAgentSession CreateTaggedSession()
    {
        var session = new BareAgentSession();
        session.SetHostedContext(new HostedSessionContext(TestUserId));
        return session;
    }

    private sealed class BareAgentSession : AgentSession
    {
        public BareAgentSession() : base(new AgentSessionStateBag()) { }
    }
}
