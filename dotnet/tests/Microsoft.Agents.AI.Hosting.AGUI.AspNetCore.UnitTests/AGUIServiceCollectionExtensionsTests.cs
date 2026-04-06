// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;

namespace Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests;

/// <summary>
/// Unit tests for <see cref="Microsoft.Extensions.DependencyInjection.MicrosoftAgentAIHostingAGUIServiceCollectionExtensions"/>.
/// </summary>
public sealed class AGUIServiceCollectionExtensionsTests
{
    [Fact]
    public void AddAGUI_RegistersDefaultAgentSessionStore()
    {
        // Arrange
        ServiceCollection services = new();

        // Act
        services.AddAGUI();
        using ServiceProvider serviceProvider = services.BuildServiceProvider();

        // Assert
        AgentSessionStore sessionStore = serviceProvider.GetRequiredService<AgentSessionStore>();
        Assert.IsType<AGUIInMemorySessionStore>(sessionStore);
    }

    [Fact]
    public void AddAGUI_DoesNotOverrideCustomAgentSessionStore()
    {
        // Arrange
        ServiceCollection services = new();
        RecordingAgentSessionStore sessionStore = new();
        services.AddSingleton<AgentSessionStore>(sessionStore);

        // Act
        services.AddAGUI();
        using ServiceProvider serviceProvider = services.BuildServiceProvider();

        // Assert
        AgentSessionStore resolvedSessionStore = serviceProvider.GetRequiredService<AgentSessionStore>();
        Assert.Same(sessionStore, resolvedSessionStore);
    }

    [Fact]
    public void AddAGUI_ConfiguresDefaultInMemorySessionStoreOptions()
    {
        // Arrange
        ServiceCollection services = new();

        // Act
        services.AddAGUI(options =>
        {
            options.SizeLimit = 42;
            options.SlidingExpiration = TimeSpan.FromMinutes(5);
        });
        using ServiceProvider serviceProvider = services.BuildServiceProvider();

        // Assert
        AGUIInMemorySessionStoreOptions options = serviceProvider.GetRequiredService<IOptions<AGUIInMemorySessionStoreOptions>>().Value;
        Assert.Equal(42, options.SizeLimit);
        Assert.Equal(TimeSpan.FromMinutes(5), options.SlidingExpiration);
    }

    private sealed class RecordingAgentSessionStore : AgentSessionStore
    {
        public override ValueTask SaveSessionAsync(AIAgent agent, string conversationId, AgentSession session, CancellationToken cancellationToken = default)
            => ValueTask.CompletedTask;

        public override ValueTask<AgentSession> GetSessionAsync(AIAgent agent, string conversationId, CancellationToken cancellationToken = default)
            => throw new NotImplementedException();
    }
}