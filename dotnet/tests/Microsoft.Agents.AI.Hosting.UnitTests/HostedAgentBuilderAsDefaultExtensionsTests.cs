// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
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

    // These three tests pin how Microsoft.Extensions.DependencyInjection disposes an agent that a keyed and a
    // non-keyed registration both resolve to: the container captures a disposable once per registration that
    // produced it and does not de-duplicate captures across registrations that resolve to the same instance. That
    // capture-per-registration behavior is what the idempotency requirement in the AsDefault remarks rests on, so a
    // future DI version that starts de-duplicating disposal fails the counts asserted here first, and the remarks
    // need updating alongside it.
    /// <summary>
    /// Verifies that a singleton default implementing <see cref="IDisposable"/> is disposed twice, once through each
    /// registration, when the provider is disposed.
    /// </summary>
    [Fact]
    public void AsDefault_SingletonImplementsIDisposable_DisposesTwice()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddAIAgent("billing", (sp, key) => new DisposableTestAgent(key), ServiceLifetime.Singleton).AsDefault();
        var provider = services.BuildServiceProvider();
        var fromKey = provider.GetRequiredKeyedService<AIAgent>("billing");
        var fromDefault = (DisposableTestAgent)provider.GetRequiredService<AIAgent>();

        // Act
        provider.Dispose();

        // Assert
        Assert.Same(fromKey, fromDefault);
        Assert.Equal(2, fromDefault.DisposeCount);
    }

    /// <summary>
    /// Verifies that a singleton default implementing only <see cref="IAsyncDisposable"/> has its <c>DisposeAsync</c>
    /// invoked twice when the provider is disposed asynchronously, mirroring the synchronous case.
    /// </summary>
    [Fact]
    public async Task AsDefault_SingletonImplementsIAsyncDisposable_DisposesAsyncTwiceAsync()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddAIAgent("billing", (sp, key) => new AsyncDisposableTestAgent(key), ServiceLifetime.Singleton).AsDefault();
        var provider = services.BuildServiceProvider();
        var fromKey = provider.GetRequiredKeyedService<AIAgent>("billing");
        var fromDefault = (AsyncDisposableTestAgent)provider.GetRequiredService<AIAgent>();

        // Act
        await provider.DisposeAsync();

        // Assert
        Assert.Same(fromKey, fromDefault);
        Assert.Equal(2, fromDefault.DisposeAsyncCount);
    }

    /// <summary>
    /// Verifies that, without AsDefault, a singleton agent resolved only through the keyed registration is disposed
    /// exactly once, showing that the second disposal in the AsDefault case comes from the forwarding registration.
    /// </summary>
    [Fact]
    public void AddAIAgent_WithoutAsDefault_DisposesSingletonOnce()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddAIAgent("billing", (sp, key) => new DisposableTestAgent(key), ServiceLifetime.Singleton);
        var provider = services.BuildServiceProvider();
        var agent = (DisposableTestAgent)provider.GetRequiredKeyedService<AIAgent>("billing");

        // Act
        provider.Dispose();

        // Assert
        Assert.Equal(1, agent.DisposeCount);
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

    /// <summary>
    /// Verifies that AsDefault throws <see cref="ArgumentException"/>, not <see cref="NullReferenceException"/>, when a
    /// third-party <see cref="IHostedAgentBuilder"/> implementation returns a null <see cref="IHostedAgentBuilder.ServiceCollection"/>.
    /// </summary>
    [Fact]
    public void AsDefault_NullServiceCollection_ThrowsArgumentException()
    {
        // Arrange
        var builder = new NullMemberAgentBuilder(name: "billing", nullServiceCollection: true);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => builder.AsDefault());
    }

    /// <summary>
    /// Verifies that AsDefault throws <see cref="ArgumentException"/>, not the "no keyed registration"
    /// <see cref="InvalidOperationException"/>, when a third-party <see cref="IHostedAgentBuilder"/> implementation
    /// returns a null <see cref="IHostedAgentBuilder.Name"/>, and that the failing call adds no descriptor.
    /// </summary>
    [Fact]
    public void AsDefault_NullName_ThrowsArgumentException()
    {
        // Arrange
        var builder = new NullMemberAgentBuilder(name: null, nullServiceCollection: false);

        // Act & Assert
        Assert.Throws<ArgumentException>(() => builder.AsDefault());
        Assert.Empty(builder.ServiceCollection);
    }

    /// <summary>
    /// Verifies that AsDefault throws when the last-registered keyed <see cref="AIAgent"/> registration for the
    /// builder's name is shorter-lived than the builder, and that the failing call adds no descriptor.
    /// </summary>
    [Fact]
    public void AsDefault_LastKeyedRegistrationShorterLivedThanBuilder_ThrowsInvalidOperationException()
    {
        // Arrange
        var services = new ServiceCollection();
        var first = services.AddAIAgent("billing", (sp, key) => new TestEchoAgent(name: key), ServiceLifetime.Singleton);
        services.AddAIAgent("billing", (sp, key) => new TestEchoAgent(name: key), ServiceLifetime.Scoped);
        var countBeforeAsDefault = services.Count;

        // Act
        var exception = Assert.Throws<InvalidOperationException>(() => first.AsDefault());

        // Assert
        Assert.Contains("'billing'", exception.Message, StringComparison.Ordinal);
        Assert.Contains("Scoped", exception.Message, StringComparison.Ordinal);
        Assert.Contains("Singleton", exception.Message, StringComparison.Ordinal);
        Assert.Equal(countBeforeAsDefault, services.Count);
    }

    /// <summary>
    /// Verifies that AsDefault scans for the LAST keyed <see cref="AIAgent"/> registration under the builder's name,
    /// which is the one DI actually resolves, and does not throw when that one is at least as long-lived as the builder
    /// even though an earlier, shorter-lived keyed registration under the same name exists.
    /// </summary>
    [Fact]
    public void AsDefault_LastKeyedRegistrationAtLeastAsLongLivedAsBuilder_DoesNotThrow()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddAIAgent("billing", (sp, key) => new TestEchoAgent(name: key), ServiceLifetime.Scoped);
        var second = services.AddAIAgent("billing", (sp, key) => new TestEchoAgent(name: key), ServiceLifetime.Singleton);

        // Act
        second.AsDefault();

        // Assert
        _ = Assert.Single(services, d => d.ServiceType == typeof(AIAgent) && !d.IsKeyedService);
    }

    /// <summary>
    /// Verifies that AsDefault throws exactly when the keyed registration's lifetime is shorter than the builder's,
    /// for every (keyed lifetime, builder lifetime) pair, matching the captive-dependency rule used for tools.
    /// </summary>
    [Theory]
    [InlineData(ServiceLifetime.Singleton, ServiceLifetime.Singleton, false)]
    [InlineData(ServiceLifetime.Singleton, ServiceLifetime.Scoped, false)]
    [InlineData(ServiceLifetime.Singleton, ServiceLifetime.Transient, false)]
    [InlineData(ServiceLifetime.Scoped, ServiceLifetime.Singleton, true)]
    [InlineData(ServiceLifetime.Scoped, ServiceLifetime.Scoped, false)]
    [InlineData(ServiceLifetime.Scoped, ServiceLifetime.Transient, false)]
    [InlineData(ServiceLifetime.Transient, ServiceLifetime.Singleton, true)]
    [InlineData(ServiceLifetime.Transient, ServiceLifetime.Scoped, true)]
    [InlineData(ServiceLifetime.Transient, ServiceLifetime.Transient, false)]
    public void AsDefault_KeyedAndBuilderLifetimeCombinations_ThrowsOnlyWhenKeyedIsShorterLived(
        ServiceLifetime keyedLifetime, ServiceLifetime builderLifetime, bool expectThrow)
    {
        // Arrange
        var builder = new StandaloneAgentBuilder("billing", builderLifetime);
        builder.ServiceCollection.Add(new ServiceDescriptor(
            typeof(AIAgent), "billing", (sp, key) => new TestEchoAgent(name: key as string), keyedLifetime));

        // Act & Assert
        if (expectThrow)
        {
            var exception = Assert.Throws<InvalidOperationException>(() => builder.AsDefault());
            Assert.Contains("'billing'", exception.Message, StringComparison.Ordinal);
            Assert.Contains(keyedLifetime.ToString(), exception.Message, StringComparison.Ordinal);
            Assert.Contains(builderLifetime.ToString(), exception.Message, StringComparison.Ordinal);
            Assert.DoesNotContain(builder.ServiceCollection, d => d.ServiceType == typeof(AIAgent) && !d.IsKeyedService);
        }
        else
        {
            builder.AsDefault();
            _ = Assert.Single(builder.ServiceCollection, d => d.ServiceType == typeof(AIAgent) && !d.IsKeyedService);
        }
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
    private sealed class StandaloneAgentBuilder(string name, ServiceLifetime lifetime = ServiceLifetime.Singleton) : IHostedAgentBuilder
    {
        public string Name { get; } = name;

        public IServiceCollection ServiceCollection { get; } = new ServiceCollection();

        public ServiceLifetime Lifetime { get; } = lifetime;
    }

    /// <summary>
    /// A hand-rolled <see cref="IHostedAgentBuilder"/> standing in for a third-party implementation that violates the
    /// interface's non-nullable contract by returning a null <see cref="Name"/> or <see cref="ServiceCollection"/>.
    /// </summary>
    private sealed class NullMemberAgentBuilder : IHostedAgentBuilder
    {
        public NullMemberAgentBuilder(string? name, bool nullServiceCollection)
        {
            // null! simulates a third-party implementation that ignores the interface's non-nullable annotation.
            this.Name = name!;
            this.ServiceCollection = nullServiceCollection ? null! : new ServiceCollection();
        }

        public string Name { get; }

        public IServiceCollection ServiceCollection { get; }

        public ServiceLifetime Lifetime => ServiceLifetime.Singleton;
    }

    /// <summary>
    /// Wraps a <see cref="TestEchoAgent"/> to supply the abstract <see cref="AIAgent"/> members, so disposal fakes only
    /// need to add the disposal interface and its counter.
    /// </summary>
    private abstract class WrappingTestAgent(string name) : AIAgent
    {
        private readonly TestEchoAgent _inner = new(name: name);

        public override string? Name => this._inner.Name;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => this._inner.CreateSessionAsync(cancellationToken);

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => this._inner.SerializeSessionAsync(session, jsonSerializerOptions, cancellationToken);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => this._inner.DeserializeSessionAsync(serializedState, jsonSerializerOptions, cancellationToken);

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => this._inner.RunAsync(messages, session, options, cancellationToken);

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => this._inner.RunStreamingAsync(messages, session, options, cancellationToken);
    }

    /// <summary>
    /// A <see cref="WrappingTestAgent"/> that counts synchronous <see cref="Dispose"/> calls, used to pin how many
    /// times the container disposes a default agent's instance.
    /// </summary>
    private sealed class DisposableTestAgent(string name) : WrappingTestAgent(name), IDisposable
    {
        public int DisposeCount { get; private set; }

        public void Dispose() => this.DisposeCount++;
    }

    /// <summary>
    /// A <see cref="WrappingTestAgent"/> that implements only <see cref="IAsyncDisposable"/> and counts
    /// <see cref="DisposeAsync"/> calls, used to pin how many times the container disposes a default agent's instance
    /// asynchronously.
    /// </summary>
    private sealed class AsyncDisposableTestAgent(string name) : WrappingTestAgent(name), IAsyncDisposable
    {
        public int DisposeAsyncCount { get; private set; }

        public ValueTask DisposeAsync()
        {
            this.DisposeAsyncCount++;
            return default;
        }
    }
}
