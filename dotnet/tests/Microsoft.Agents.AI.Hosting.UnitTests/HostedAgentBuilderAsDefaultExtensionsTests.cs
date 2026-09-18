// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;

namespace Microsoft.Agents.AI.Hosting.UnitTests;

/// <summary>
/// Unit tests for <see cref="HostedAgentBuilderExtensions.AsDefault(IHostedAgentBuilder)"/>.
/// </summary>
public sealed class HostedAgentBuilderAsDefaultExtensionsTests
{
    /// <summary>
    /// Verifies that AsDefault returns the same builder instance so that further With* calls chain.
    /// </summary>
    [Fact]
    public void AsDefault_ReturnsSameBuilder()
    {
        // Arrange
        var services = new ServiceCollection();
        var builder = services.AddAIAgent("writer", (sp, key) => new TestEchoAgent(name: key));

        // Act
        var returned = builder.AsDefault();

        // Assert
        Assert.Same(builder, returned);
    }

    /// <summary>
    /// Verifies that AsDefault throws <see cref="ArgumentNullException"/> for a null builder.
    /// </summary>
    [Fact]
    public void AsDefault_NullBuilder_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => HostedAgentBuilderExtensions.AsDefault(null!));
    }

    /// <summary>
    /// Verifies that after AsDefault the agent resolves without a key, exactly once, and keyed resolution still works.
    /// </summary>
    [Fact]
    public void AsDefault_NonKeyedResolution_ReturnsRegisteredAgent()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddAIAgent("writer", (sp, key) => new TestEchoAgent(name: key)).AsDefault();

        // Act
        using var provider = services.BuildServiceProvider();

        // Assert
        Assert.Equal("writer", provider.GetRequiredService<AIAgent>().Name);
        Assert.Single(provider.GetServices<AIAgent>());
        _ = provider.GetRequiredKeyedService<AIAgent>("writer");
    }

    /// <summary>
    /// Verifies that without AsDefault no non-keyed <see cref="AIAgent"/> registration exists.
    /// </summary>
    [Fact]
    public void AddAIAgent_WithoutAsDefault_AddsNoNonKeyedRegistration()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddAIAgent("writer", (sp, key) => new TestEchoAgent(name: key));

        // Act
        using var provider = services.BuildServiceProvider();

        // Assert
        Assert.DoesNotContain(services, d => d.ServiceType == typeof(AIAgent) && !d.IsKeyedService);
        Assert.Null(provider.GetService<AIAgent>());
    }

    /// <summary>
    /// Verifies that a singleton default resolves to the same instance as the keyed registration and runs the factory once.
    /// </summary>
    [Fact]
    public void AsDefault_SingletonLifetime_ForwardsToKeyedRegistration()
    {
        // Arrange
        var factoryInvocations = 0;
        var services = new ServiceCollection();
        services.AddAIAgent(
            "a",
            (sp, key) =>
            {
                factoryInvocations++;
                return new TestEchoAgent(name: key);
            },
            ServiceLifetime.Singleton).AsDefault();

        using var provider = services.BuildServiceProvider();

        // Act
        var fromDefault = provider.GetRequiredService<AIAgent>();
        var fromKey = provider.GetRequiredKeyedService<AIAgent>("a");

        // Assert
        Assert.Same(fromDefault, fromKey);
        Assert.Equal(1, factoryInvocations);
    }

    /// <summary>
    /// Verifies that a scoped default is shared inside a scope, differs between scopes, and runs the factory once per scope.
    /// </summary>
    [Fact]
    public void AsDefault_ScopedLifetime_SharesInstanceWithinScope()
    {
        // Arrange
        var factoryInvocations = 0;
        var services = new ServiceCollection();
        services.AddAIAgent(
            "a",
            (sp, key) =>
            {
                factoryInvocations++;
                return new TestEchoAgent(name: key);
            },
            ServiceLifetime.Scoped).AsDefault();

        using var provider = services.BuildServiceProvider();

        // Act & Assert
        AIAgent firstScopeAgent;
        using (var firstScope = provider.CreateScope())
        {
            firstScopeAgent = firstScope.ServiceProvider.GetRequiredService<AIAgent>();
            Assert.Same(firstScopeAgent, firstScope.ServiceProvider.GetRequiredKeyedService<AIAgent>("a"));
            Assert.Equal(1, factoryInvocations);
        }

        using (var secondScope = provider.CreateScope())
        {
            var secondScopeAgent = secondScope.ServiceProvider.GetRequiredService<AIAgent>();
            Assert.NotSame(firstScopeAgent, secondScopeAgent);
            Assert.Equal(2, factoryInvocations);
        }
    }

    /// <summary>
    /// Verifies that a transient default produces a new instance, and one factory invocation, per resolution.
    /// </summary>
    [Fact]
    public void AsDefault_TransientLifetime_CreatesInstancePerResolution()
    {
        // Arrange
        var factoryInvocations = 0;
        var services = new ServiceCollection();
        services.AddAIAgent(
            "a",
            (sp, key) =>
            {
                factoryInvocations++;
                return new TestEchoAgent(name: key);
            },
            ServiceLifetime.Transient).AsDefault();

        using var provider = services.BuildServiceProvider();

        // Act
        var first = provider.GetRequiredService<AIAgent>();
        var second = provider.GetRequiredService<AIAgent>();

        // Assert
        Assert.NotSame(first, second);
        Assert.Equal(2, factoryInvocations);
    }

    /// <summary>
    /// Verifies that the descriptor added by AsDefault is a single non-keyed <see cref="AIAgent"/> registration
    /// carrying the builder lifetime.
    /// </summary>
    [Theory]
    [InlineData(ServiceLifetime.Singleton)]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public void AsDefault_DescriptorShape_MatchesBuilderLifetime(ServiceLifetime lifetime)
    {
        // Arrange
        var services = new ServiceCollection();
        var builder = services.AddAIAgent("a", (sp, key) => new TestEchoAgent(name: key), lifetime);

        // Act
        builder.AsDefault();

        // Assert
        var descriptor = Assert.Single(services, d => d.ServiceType == typeof(AIAgent) && !d.IsKeyedService);
        Assert.Equal(builder.Lifetime, descriptor.Lifetime);
    }

    /// <summary>
    /// Verifies that a second AsDefault on another builder throws, that the message names both agents, and that the
    /// failing call adds no descriptor.
    /// </summary>
    [Fact]
    public void AsDefault_SecondDefaultOnAnotherBuilder_ThrowsInvalidOperationException()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddAIAgent("a", (sp, key) => new TestEchoAgent(name: key)).AsDefault();
        var second = services.AddAIAgent("b", (sp, key) => new TestEchoAgent(name: key));

        // Act
        var exception = Assert.Throws<InvalidOperationException>(() => second.AsDefault());

        // Assert
        Assert.Contains("'b'", exception.Message, StringComparison.Ordinal);
        Assert.Contains("'a'", exception.Message, StringComparison.Ordinal);
        _ = Assert.Single(services, d => d.ServiceType == typeof(AIAgent) && !d.IsKeyedService);
    }

    /// <summary>
    /// Verifies that a raw non-keyed <see cref="AIAgent"/> registered between two AsDefault calls does not mask the
    /// earlier default: the second AsDefault still throws and the message names both agents.
    /// </summary>
    [Fact]
    public void AsDefault_SecondDefaultWithInterleavedRawRegistration_ThrowsInvalidOperationException()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddAIAgent("a", (sp, key) => new TestEchoAgent(name: key)).AsDefault();
        services.AddSingleton<AIAgent>(new TestEchoAgent(name: "raw"));
        var second = services.AddAIAgent("b", (sp, key) => new TestEchoAgent(name: key));

        // Act
        var exception = Assert.Throws<InvalidOperationException>(() => second.AsDefault());

        // Assert
        Assert.Contains("'b'", exception.Message, StringComparison.Ordinal);
        Assert.Contains("'a'", exception.Message, StringComparison.Ordinal);
    }

    /// <summary>
    /// Verifies that a raw non-keyed <see cref="AIAgent"/> instance registration does not make AsDefault throw and is
    /// superseded by it under the standard last-registration-wins rule.
    /// </summary>
    [Fact]
    public void AsDefault_RawNonKeyedRegistrationExists_IsSupersededByDefault()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddSingleton<AIAgent>(new TestEchoAgent(name: "raw"));

        // Act
        services.AddAIAgent("b", (sp, key) => new TestEchoAgent(name: key)).AsDefault();

        // Assert
        using var provider = services.BuildServiceProvider();
        Assert.Equal("b", provider.GetRequiredService<AIAgent>().Name);
        Assert.Equal(2, provider.GetServices<AIAgent>().Count());
    }

    /// <summary>
    /// Verifies that a factory-registered non-keyed <see cref="AIAgent"/> does not make AsDefault throw and is
    /// superseded by it under the standard last-registration-wins rule.
    /// </summary>
    [Fact]
    public void AsDefault_RawNonKeyedFactoryRegistrationExists_IsSupersededByDefault()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddSingleton<AIAgent>(sp => new TestEchoAgent(name: "raw"));

        // Act
        services.AddAIAgent("b", (sp, key) => new TestEchoAgent(name: key)).AsDefault();

        // Assert
        using var provider = services.BuildServiceProvider();
        Assert.Equal("b", provider.GetRequiredService<AIAgent>().Name);
        Assert.Equal(2, provider.GetServices<AIAgent>().Count());
    }

    /// <summary>
    /// Verifies that calling AsDefault twice on the same builder throws; there is no idempotency special case.
    /// </summary>
    [Fact]
    public void AsDefault_CalledTwiceOnSameBuilder_ThrowsInvalidOperationException()
    {
        // Arrange
        var services = new ServiceCollection();
        var builder = services.AddAIAgent("a", (sp, key) => new TestEchoAgent(name: key)).AsDefault();

        // Act
        var exception = Assert.Throws<InvalidOperationException>(() => builder.AsDefault());

        // Assert
        Assert.Contains("'a'", exception.Message, StringComparison.Ordinal);
    }

    /// <summary>
    /// Verifies that the default agent exposes the builder tools whichever order AsDefault and WithAITool are called in.
    /// </summary>
    [Fact]
    public void AsDefault_BeforeOrAfterWithAITool_ResolvesSameTools()
    {
        // Arrange
        var tool = new DummyAITool();

        var defaultBeforeTool = new ServiceCollection();
        defaultBeforeTool.AddSingleton<IChatClient>(new MockChatClient());
        defaultBeforeTool.AddAIAgent("writer", "instructions").AsDefault().WithAITool(tool);

        var defaultAfterTool = new ServiceCollection();
        defaultAfterTool.AddSingleton<IChatClient>(new MockChatClient());
        defaultAfterTool.AddAIAgent("writer", "instructions").WithAITool(tool).AsDefault();

        // Act
        using var providerWithDefaultBeforeTool = defaultBeforeTool.BuildServiceProvider();
        using var providerWithDefaultAfterTool = defaultAfterTool.BuildServiceProvider();

        // Assert
        Assert.Contains(tool, ResolveToolsFromDefaultAgent(providerWithDefaultBeforeTool));
        Assert.Contains(tool, ResolveToolsFromDefaultAgent(providerWithDefaultAfterTool));
    }

    /// <summary>
    /// Verifies that a raw non-keyed registration added after AsDefault wins and does not throw.
    /// </summary>
    [Fact]
    public void AsDefault_LaterRawRegistration_Wins()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddAIAgent("a", (sp, key) => new TestEchoAgent(name: key)).AsDefault();
        var other = new TestEchoAgent(name: "other");
        services.AddSingleton<AIAgent>(other);

        // Act
        using var provider = services.BuildServiceProvider();

        // Assert
        Assert.Same(other, provider.GetRequiredService<AIAgent>());
    }

    /// <summary>
    /// Verifies that keyed enumeration plus the non-keyed default yields a single distinct singleton instance.
    /// </summary>
    [Fact]
    public void AsDefault_KeyedAndDefaultResolutions_YieldOneInstance()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddAIAgent("a", (sp, key) => new TestEchoAgent(name: key)).AsDefault();

        using var provider = services.BuildServiceProvider();

        // Act
        var distinctAgents = new HashSet<object>(ReferenceEqualityComparer.Instance);
        foreach (var keyedAgent in provider.GetKeyedServices<AIAgent>(KeyedService.AnyKey))
        {
            distinctAgents.Add(keyedAgent);
        }

        distinctAgents.Add(provider.GetRequiredService<AIAgent>());

        // Assert
        Assert.Single(distinctAgents);
    }

    /// <summary>
    /// Verifies that a scoped default resolved from the root of a scope-validating provider throws, as keyed resolution does.
    /// </summary>
    [Fact]
    public void AsDefault_ScopedAgentFromRoot_ThrowsWhenScopesValidated()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddAIAgent("a", (sp, key) => new TestEchoAgent(name: key), ServiceLifetime.Scoped).AsDefault();

        // Act
        using var provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });

        // Assert
        Assert.Throws<InvalidOperationException>(() => provider.GetRequiredService<AIAgent>());
    }

    /// <summary>
    /// Verifies that AsDefault throws when no keyed <see cref="AIAgent"/> registration exists under the builder's name,
    /// and that it adds nothing to the service collection.
    /// </summary>
    [Fact]
    public void AsDefault_NoKeyedRegistrationForName_ThrowsInvalidOperationException()
    {
        // Arrange
        var builder = new StandaloneAgentBuilder("ghost");

        // Act
        var exception = Assert.Throws<InvalidOperationException>(() => builder.AsDefault());

        // Assert
        Assert.Contains("ghost", exception.Message, StringComparison.Ordinal);
        Assert.Empty(builder.ServiceCollection);
    }

    private static IList<AITool> ResolveToolsFromDefaultAgent(IServiceProvider serviceProvider)
    {
        var agent = serviceProvider.GetRequiredService<AIAgent>() as ChatClientAgent;
        Assert.NotNull(agent?.ChatOptions?.Tools);
        return agent.ChatOptions.Tools;
    }

    /// <summary>
    /// A hand-rolled <see cref="IHostedAgentBuilder"/> over an empty service collection: the only way to reach
    /// <c>AsDefault()</c> without the keyed registration that <c>AddAIAgent</c> adds.
    /// </summary>
    private sealed class StandaloneAgentBuilder(string name) : IHostedAgentBuilder
    {
        public string Name { get; } = name;

        public IServiceCollection ServiceCollection { get; } = new ServiceCollection();

        public ServiceLifetime Lifetime => ServiceLifetime.Singleton;
    }
}
