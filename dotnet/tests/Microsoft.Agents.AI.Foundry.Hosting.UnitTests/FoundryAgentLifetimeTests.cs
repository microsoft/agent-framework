// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Covers how the one agent a container serves is created and disposed for each lifetime, the
/// <c>AddFoundryResponses</c> overloads that take an agent or a factory for it, and
/// <c>AddFoundryAgentSessionStore</c>, which registers the session store separately from the agent.
/// </summary>
public sealed class FoundryAgentLifetimeTests
{
    private const string AgentName = "lifetime-agent";
    private const string TelemetrySourceName = "Microsoft.Agents.AI.Foundry.Hosting.UnitTests.Lifetime";

    [Theory]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public async Task CreateAsync_PerRunFactoryAgent_CreatesOnePerResponseAndDisposesItAsync(ServiceLifetime lifetime)
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        AgentFrameworkResponseHandler handler = CreateHandler(services, _ => new TrackingAgent(log), lifetime);

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);

        // Assert
        Assert.Equal(2, log.Created.Count);
        Assert.NotSame(log.Created.First(), log.Created.Last());
        Assert.All(log.Created, agent => Assert.Equal(1, agent.RunCount));
        Assert.All(log.Created, agent => Assert.Equal(1, agent.DisposeCount));
        Assert.All(log.Created, agent => Assert.False(agent.WasDisposedDuringRun));
    }

    [Fact]
    public async Task CreateAsync_SingletonFactoryAgent_IsCreatedOnceAndNotDisposedPerRunAsync()
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        AgentFrameworkResponseHandler handler = CreateHandler(services, _ => new TrackingAgent(log), ServiceLifetime.Singleton);

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);

        // Assert
        TrackingAgent agent = Assert.Single(log.Created);
        Assert.Equal(2, agent.RunCount);
        Assert.False(agent.IsDisposed);
    }

    [Fact]
    public async Task CreateAsync_InstanceAgent_IsReusedAndNotDisposedAsync()
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var agent = new TrackingAgent(log);
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        var handler = new AgentFrameworkResponseHandler(
            services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true }),
            new FoundryHostedAgentSource(agent),
            NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);

        // Assert
        Assert.Same(agent, Assert.Single(log.Created));
        Assert.Equal(2, agent.RunCount);
        Assert.False(agent.IsDisposed);
    }

    [Fact]
    public async Task CreateAsync_ScopedAgent_StaysAliveUntilTheEventStreamEndsAsync()
    {
        // Arrange: the agent waits mid-run, as a long background run would.
        var log = new AgentLifetimeLog();
        var gate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        AgentFrameworkResponseHandler handler = CreateHandler(services, _ => new TrackingAgent(log, gate), ServiceLifetime.Scoped);

        // Act
        Task run = Task.Run(() => DrainAsync(handler));
        TrackingAgent agent = await log.RunStarted.Task.WaitAsync(TimeSpan.FromSeconds(10));
        bool disposedWhileRunning = agent.IsDisposed;
        gate.SetResult();
        await run.WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.False(disposedWhileRunning);
        Assert.False(agent.WasDisposedDuringRun);
        Assert.True(agent.IsDisposed);
    }

    [Fact]
    public async Task CreateAsync_EnumerationStoppedEarly_DisposesScopedAgentAsync()
    {
        // Arrange: a client disconnect or cancellation stops reading the stream early.
        var log = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        AgentFrameworkResponseHandler handler = CreateHandler(services, _ => new TrackingAgent(log), ServiceLifetime.Scoped);
        IAsyncEnumerator<ResponseStreamEvent> enumerator = handler
            .CreateAsync(CreateRequest(), CreateContext(), CancellationToken.None)
            .GetAsyncEnumerator();

        // Act
        Assert.True(await enumerator.MoveNextAsync());
        TrackingAgent agent = Assert.Single(log.Created);
        bool disposedBeforeStop = agent.IsDisposed;
        await enumerator.DisposeAsync();

        // Assert
        Assert.False(disposedBeforeStop);
        Assert.True(agent.IsDisposed);
    }

    [Fact]
    public async Task CreateAsync_ScopedFactory_ResolvesDependenciesFromTheRunScopeAsync()
    {
        // Arrange: scopes are validated, so a scoped dependency resolves only from a run's scope.
        var dependencies = new ConcurrentQueue<ScopedDependency>();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        services.AddScoped(_ => new ScopedDependency());
        AgentFrameworkResponseHandler handler = CreateHandler(
            services,
            sp =>
            {
                dependencies.Enqueue(sp.GetRequiredService<ScopedDependency>());
                return new TrackingAgent(new AgentLifetimeLog());
            },
            ServiceLifetime.Scoped);

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);

        // Assert: each run has its own dependency, disposed with the run's scope.
        Assert.Equal(2, dependencies.Count);
        Assert.NotSame(dependencies.First(), dependencies.Last());
        Assert.All(dependencies, dependency => Assert.True(dependency.IsDisposed));
    }

    [Fact]
    public async Task CreateAsync_SingletonFactoryResolvingAScopedService_FailsAsDependencyInjectionWouldAsync()
    {
        // Arrange: a singleton agent is created from the root provider, which cannot supply a scoped service.
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        services.AddScoped(_ => new ScopedDependency());
        AgentFrameworkResponseHandler handler = CreateHandler(
            services,
            sp =>
            {
                _ = sp.GetRequiredService<ScopedDependency>();
                return new TrackingAgent(new AgentLifetimeLog());
            },
            ServiceLifetime.Singleton);

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => DrainAsync(handler));
        Assert.Contains(nameof(ScopedDependency), exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task CreateAsync_SingletonFactoryThrows_IsCalledAgainOnTheNextResponseAsync()
    {
        // Arrange
        int attempts = 0;
        var log = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        AgentFrameworkResponseHandler handler = CreateHandler(
            services,
            _ => Interlocked.Increment(ref attempts) == 1
                ? throw new InvalidOperationException("transient failure")
                : new TrackingAgent(log),
            ServiceLifetime.Singleton);

        // Act
        await Assert.ThrowsAsync<InvalidOperationException>(() => DrainAsync(handler));
        await DrainAsync(handler);
        await DrainAsync(handler);

        // Assert: the failure is not cached, and the agent created afterwards is reused.
        Assert.Equal(2, attempts);
        Assert.Equal(2, Assert.Single(log.Created).RunCount);
    }

    [Fact]
    public async Task CreateAsync_ScopedSessionStore_IsCreatedPerResponseAndDisposedAsync()
    {
        // Arrange
        var stores = new ConcurrentQueue<RecordingSessionStore>();
        var services = new ServiceCollection();
        services.AddScoped<AgentSessionStore>(_ =>
        {
            var store = new RecordingSessionStore();
            stores.Enqueue(store);
            return store;
        });
        var handler = new AgentFrameworkResponseHandler(
            services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true }),
            new FoundryHostedAgentSource(new TrackingAgent(new AgentLifetimeLog())),
            NullLogger<AgentFrameworkResponseHandler>.Instance);

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);

        // Assert
        Assert.Equal(2, stores.Count);
        Assert.All(stores, store => Assert.True(store.IsDisposed));
        Assert.All(stores, store => Assert.NotEmpty(store.Identities));
    }

    [Fact]
    public async Task AddFoundryResponses_AgentsRegisteredInDI_AreNotUsedAsync()
    {
        // Arrange: agents registered in DI, including one under the name the request carries, are ignored.
        var log = new AgentLifetimeLog();
        var registeredLog = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddKeyedSingleton<AIAgent>("other", new TrackingAgent(registeredLog, name: "other"));
        services.AddSingleton<AIAgent>(new TrackingAgent(registeredLog, name: "other"));
        services.AddFoundryAgentSessionStore(new TestAgentSessionStore());
        services.AddFoundryResponses(new TrackingAgent(log));
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest("other"));
        await DrainAsync(handler);

        // Assert
        Assert.Equal(2, Assert.Single(log.Created).RunCount);
        Assert.All(registeredLog.Created, agent => Assert.Equal(0, agent.RunCount));
    }

    [Theory]
    [InlineData(ServiceLifetime.Singleton)]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public async Task AddFoundryResponses_Factory_UsesTheInstanceOverloadStorageIdentityAsync(ServiceLifetime lifetime)
    {
        // Arrange: the instance overload stores sessions under the agent name.
        var instanceStore = new RecordingSessionStore();
        var instanceServices = new ServiceCollection();
        instanceServices.AddLogging();
        instanceServices.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog()), instanceStore);
        AgentFrameworkResponseHandler instanceHandler = ResolveHandler(instanceServices);
        await DrainAsync(instanceHandler);
        string instanceIdentity = Assert.Single(instanceStore.Identities.Distinct());

        var factoryStore = new RecordingSessionStore();
        var factoryServices = new ServiceCollection();
        factoryServices.AddLogging();
        factoryServices.AddFoundryAgentSessionStore(factoryStore);
        factoryServices.AddFoundryResponses(_ => new TrackingAgent(new AgentLifetimeLog()), lifetime, LifetimeOnlyOptions());
        AgentFrameworkResponseHandler factoryHandler = ResolveHandler(factoryServices);

        // Act: one request names an agent and one does not; neither changes the storage location.
        await DrainAsync(factoryHandler, CreateRequest("another-name"));
        await DrainAsync(factoryHandler);

        // Assert: every lifetime and both request shapes read and write the same sessions.
        Assert.Equal($"name:{AgentName}", instanceIdentity);
        Assert.All(factoryStore.Identities, identity => Assert.Equal(instanceIdentity, identity));
    }

    [Fact]
    public async Task AddFoundryResponses_UnnamedAgent_UsesTheDefaultStorageIdentityAsync()
    {
        // Arrange
        var store = new RecordingSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog(), name: null), store);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler);

        // Assert
        Assert.Equal("default", Assert.Single(store.Identities.Distinct()));
    }

    [Theory]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public async Task AddFoundryResponses_Factory_CreatesOneAgentPerResponseAsync(ServiceLifetime lifetime)
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryAgentSessionStore(new TestAgentSessionStore());
        services.AddFoundryResponses(_ => new TrackingAgent(log), lifetime, LifetimeOnlyOptions());
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);

        // Assert
        Assert.Equal(2, log.Created.Count);
        Assert.All(log.Created, agent => Assert.Equal(1, agent.RunCount));
        Assert.All(log.Created, agent => Assert.True(agent.IsDisposed));
    }

    [Fact]
    public async Task AddFoundryResponses_SingletonFactory_CreatesOneAgentForTheProcessAsync()
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryAgentSessionStore(new TestAgentSessionStore());
        services.AddFoundryResponses(_ => new TrackingAgent(log), ServiceLifetime.Singleton);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);

        // Assert
        TrackingAgent agent = Assert.Single(log.Created);
        Assert.Equal(2, agent.RunCount);
        Assert.False(agent.IsDisposed);
    }

    [Theory]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public async Task AddFoundryAgentSessionStore_Factory_CreatesOneStorePerResponseIndependentlyOfTheAgentAsync(ServiceLifetime lifetime)
    {
        // Arrange: a singleton agent with a store that has its own, shorter lifetime.
        var log = new AgentLifetimeLog();
        var stores = new ConcurrentQueue<RecordingSessionStore>();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(_ => new TrackingAgent(log));
        services.AddFoundryAgentSessionStore(
            _ =>
            {
                var store = new RecordingSessionStore();
                stores.Enqueue(store);
                return store;
            },
            lifetime);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);

        // Assert: each run uses one store, which is disposed when the run ends, while the agent lives on.
        Assert.Equal(2, stores.Count);
        Assert.All(stores, store => Assert.Equal(1, store.DisposeCount));
        Assert.All(stores, store => Assert.NotEmpty(store.Identities));
        Assert.All(stores.SelectMany(store => store.Identities), identity => Assert.Equal($"name:{AgentName}", identity));
        TrackingAgent agent = Assert.Single(log.Created);
        Assert.False(agent.IsDisposed);
    }

    [Fact]
    public async Task AddFoundryAgentSessionStore_Factory_DefaultsToOneStoreForTheProcessAsync()
    {
        // Arrange: a scoped agent with a store registered without a lifetime.
        var stores = new ConcurrentQueue<RecordingSessionStore>();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(_ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped, LifetimeOnlyOptions());
        services.AddFoundryAgentSessionStore(_ =>
        {
            var store = new RecordingSessionStore();
            stores.Enqueue(store);
            return store;
        });
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);

        // Assert
        RecordingSessionStore store = Assert.Single(stores);
        Assert.False(store.IsDisposed);
    }

    [Fact]
    public async Task AddFoundryAgentSessionStore_Instance_IsNeverDisposedByTheContainerAsync()
    {
        // Arrange: a shared store object used by a scoped agent.
        var store = new RecordingSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(_ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped, LifetimeOnlyOptions());
        services.AddFoundryAgentSessionStore(store);
        ServiceProvider provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        var handler = Assert.IsType<AgentFrameworkResponseHandler>(provider.GetRequiredService<ResponseHandler>());

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);
        await provider.DisposeAsync();

        // Assert: the caller owns the store, so neither the response runs nor shutdown dispose it.
        Assert.NotEmpty(store.Identities);
        Assert.Equal(0, store.DisposeCount);
    }

    [Fact]
    public async Task AddFoundryAgentSessionStore_FactoryReturnsNull_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(_ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped, LifetimeOnlyOptions());
        services.AddFoundryAgentSessionStore(_ => null!, ServiceLifetime.Scoped);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => DrainAsync(handler));
        Assert.Contains("session store factory", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AddFoundryResponses_FactoryReturnsNull_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryAgentSessionStore(new TestAgentSessionStore());
        services.AddFoundryResponses(_ => null!, ServiceLifetime.Scoped);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => DrainAsync(handler));
        Assert.Contains("agent factory", exception.Message, StringComparison.Ordinal);
        Assert.Contains("returned null", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AddFoundryAgentSessionStore_InvalidArguments_Throw()
    {
        // Arrange
        var services = new ServiceCollection();
        var store = new TestAgentSessionStore();
        Func<IServiceProvider, AgentSessionStore> nullFactory = null!;

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => ((IServiceCollection)null!).AddFoundryAgentSessionStore(store));
        Assert.Throws<ArgumentNullException>(() => services.AddFoundryAgentSessionStore(null!));
        Assert.Throws<ArgumentNullException>(() => services.AddFoundryAgentSessionStore(nullFactory));
        Assert.Throws<ArgumentOutOfRangeException>(() => services.AddFoundryAgentSessionStore(_ => store, (ServiceLifetime)42));
        Assert.Throws<ArgumentNullException>(() => ((IHostApplicationBuilder)null!).AddFoundryAgentSessionStore(store));
        Assert.Empty(services);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(ServiceLifetime.Singleton)]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public void AddFoundryResponses_RegistersTheAgentSourceAndNoAgent(ServiceLifetime? factoryLifetime)
    {
        // Arrange
        var services = new ServiceCollection();

        // Act
        if (factoryLifetime is { } lifetime)
        {
            services.AddFoundryResponses(_ => new TrackingAgent(new AgentLifetimeLog()), lifetime);
        }
        else
        {
            services.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog()));
        }

        // Assert: the agent source is a singleton, the agent is not in DI, and the default store is added.
        ServiceDescriptor source = Assert.Single(services, d => d.ServiceType == typeof(FoundryHostedAgentSource));
        Assert.Equal(ServiceLifetime.Singleton, source.Lifetime);
        Assert.DoesNotContain(services, d => d.ServiceType == typeof(AIAgent));
        ServiceDescriptor defaultStore = Assert.Single(services, d => d.ServiceType == typeof(AgentSessionStore));
        Assert.Equal(ServiceLifetime.Singleton, defaultStore.Lifetime);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void AddFoundryAgentSessionStore_ReplacesTheDefaultStoreInAnyOrder(bool registerStoreFirst)
    {
        // Arrange
        var store = new TestAgentSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();

        // Act
        if (registerStoreFirst)
        {
            services.AddFoundryAgentSessionStore(store);
            services.AddFoundryResponses(_ => new TrackingAgent(new AgentLifetimeLog()));
        }
        else
        {
            services.AddFoundryResponses(_ => new TrackingAgent(new AgentLifetimeLog()));
            services.AddFoundryAgentSessionStore(store);
        }

        using ServiceProvider provider = services.BuildServiceProvider();

        // Assert
        Assert.Single(services, d => d.ServiceType == typeof(AgentSessionStore));
        Assert.Same(store, provider.GetRequiredService<AgentSessionStore>());
    }

    [Fact]
    public void AddFoundryAgentSessionStore_CalledTwice_TheLastCallWins()
    {
        // Arrange
        var first = new TestAgentSessionStore();
        var second = new TestAgentSessionStore();
        var services = new ServiceCollection();

        // Act
        services.AddFoundryAgentSessionStore(first);
        services.AddFoundryAgentSessionStore(_ => second, ServiceLifetime.Scoped);
        using ServiceProvider provider = services.BuildServiceProvider();
        using IServiceScope scope = provider.CreateScope();

        // Assert
        ServiceDescriptor descriptor = Assert.Single(services, d => d.ServiceType == typeof(AgentSessionStore));
        Assert.Equal(ServiceLifetime.Scoped, descriptor.Lifetime);
        Assert.Same(second, scope.ServiceProvider.GetRequiredService<AgentSessionStore>());
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task AddFoundryResponses_StorePassedWithTheAgent_TheLastRegisteredStoreIsUsedAsync(bool passStoreLast)
    {
        // Arrange
        var storePassedWithAgent = new RecordingSessionStore();
        var storeRegistered = new RecordingSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();
        if (passStoreLast)
        {
            services.AddFoundryAgentSessionStore(storeRegistered);
            services.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog()), storePassedWithAgent);
        }
        else
        {
            services.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog()), storePassedWithAgent);
            services.AddFoundryAgentSessionStore(storeRegistered);
        }

        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler);

        // Assert
        RecordingSessionStore used = passStoreLast ? storePassedWithAgent : storeRegistered;
        RecordingSessionStore unused = passStoreLast ? storeRegistered : storePassedWithAgent;
        Assert.NotEmpty(used.Identities);
        Assert.Empty(unused.Identities);
        Assert.Single(services, d => d.ServiceType == typeof(AgentSessionStore));
    }

    [Fact]
    public void AddFoundryAgentSessionStore_HostBuilder_RegistersTheStoreWithTheRequestedLifetime()
    {
        // Arrange
        HostApplicationBuilder builder = Host.CreateApplicationBuilder();

        // Act
        builder.AddFoundryAgentSessionStore(new TestAgentSessionStore());
        builder.AddFoundryAgentSessionStore(_ => new TestAgentSessionStore(), ServiceLifetime.Transient);

        // Assert
        ServiceDescriptor descriptor = Assert.Single(builder.Services, d => d.ServiceType == typeof(AgentSessionStore));
        Assert.Equal(ServiceLifetime.Transient, descriptor.Lifetime);
    }

    [Theory]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public async Task AddFoundryResponses_Factory_DisposesEachAgentAndStoreExactlyOnceAsync(ServiceLifetime lifetime)
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var stores = new ConcurrentQueue<RecordingSessionStore>();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(_ => new TrackingAgent(log), lifetime, LifetimeOnlyOptions());
        services.AddFoundryAgentSessionStore(
            _ =>
            {
                var store = new RecordingSessionStore();
                stores.Enqueue(store);
                return store;
            },
            lifetime);
        ServiceProvider provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        var handler = Assert.IsType<AgentFrameworkResponseHandler>(provider.GetRequiredService<ResponseHandler>());

        // Act: two response runs, and one readiness lookup of the agent.
        await DrainAsync(handler);
        await DrainAsync(handler);
        await using (AsyncServiceScope scope = provider.CreateAsyncScope())
        {
            FoundryHostedAgentSource.Lease lease = await provider.GetRequiredService<FoundryHostedAgentSource>().AcquireAsync(scope.ServiceProvider);
            await lease.DisposeAsync();
            await lease.DisposeAsync();
        }

        await provider.DisposeAsync();

        // Assert
        Assert.Equal(3, log.Created.Count);
        Assert.All(log.Created, agent => Assert.Equal(1, agent.DisposeCount));
        Assert.Equal(2, stores.Count);
        Assert.All(stores, store => Assert.Equal(1, store.DisposeCount));
    }

    [Fact]
    public async Task AddFoundryResponses_SingletonFactory_DisposesTheAgentAndStoreOnceAtShutdownAsync()
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var store = new RecordingSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(_ => new TrackingAgent(log), ServiceLifetime.Singleton);
        services.AddFoundryAgentSessionStore(_ => store);
        ServiceProvider provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        var handler = Assert.IsType<AgentFrameworkResponseHandler>(provider.GetRequiredService<ResponseHandler>());

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);
        bool disposedBeforeShutdown = store.IsDisposed || log.Created.Any(agent => agent.IsDisposed);
        await provider.DisposeAsync();

        // Assert
        Assert.False(disposedBeforeShutdown);
        Assert.Equal(1, Assert.Single(log.Created).DisposeCount);
        Assert.Equal(1, store.DisposeCount);
    }

    [Fact]
    public async Task AddFoundryResponses_Instance_IsNotDisposedAtShutdownAsync()
    {
        // Arrange
        var agent = new TrackingAgent(new AgentLifetimeLog());
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryAgentSessionStore(new TestAgentSessionStore());
        services.AddFoundryResponses(agent);
        ServiceProvider provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        var handler = Assert.IsType<AgentFrameworkResponseHandler>(provider.GetRequiredService<ResponseHandler>());

        // Act
        await DrainAsync(handler);
        await provider.DisposeAsync();

        // Assert: the caller created the agent, so hosting never disposes it.
        Assert.Equal(1, agent.RunCount);
        Assert.Equal(0, agent.DisposeCount);
    }

    [Fact]
    public void AddFoundryResponses_HostBuilderFactory_RegistersTheAgentSourceAndHandler()
    {
        // Arrange
        HostApplicationBuilder builder = Host.CreateApplicationBuilder();

        // Act
        builder.AddFoundryResponses(_ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Transient);
        using ServiceProvider provider = builder.Services.BuildServiceProvider();

        // Assert
        Assert.Single(builder.Services, d => d.ServiceType == typeof(FoundryHostedAgentSource));
        Assert.DoesNotContain(builder.Services, d => d.ServiceType == typeof(AIAgent));
        Assert.IsType<AgentFrameworkResponseHandler>(provider.GetRequiredService<ResponseHandler>());
    }

    [Fact]
    public async Task AgentSource_AfterDispose_DoesNotCreateASingletonAsync()
    {
        // Arrange
        var log = new AgentLifetimeLog();
        using var provider = new ServiceCollection().BuildServiceProvider();
        var source = new FoundryHostedAgentSource(_ => new TrackingAgent(log), ServiceLifetime.Singleton, provider, requireOpenTelemetryAgent: true);

        // Act
        await source.DisposeAsync();

        // Assert
        await Assert.ThrowsAsync<ObjectDisposedException>(() => source.AcquireAsync(provider).AsTask());
        Assert.Empty(log.Created);
    }

    [Fact]
    public async Task AgentSource_SyncDisposeOfAnAsyncOnlySingleton_ThrowsAsync()
    {
        // Arrange: dependency injection throws the same way for a service it can only dispose asynchronously.
        var log = new AgentLifetimeLog();
        using var provider = new ServiceCollection().BuildServiceProvider();
        var source = new FoundryHostedAgentSource(_ => new TrackingAgent(log), ServiceLifetime.Singleton, provider, requireOpenTelemetryAgent: true);
        _ = await source.AcquireAsync(provider);

        // Act & Assert
        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(source.Dispose);
        Assert.Contains("DisposeAsync", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AgentSource_InvalidArguments_ThrowAsync()
    {
        // Arrange
        using var provider = new ServiceCollection().BuildServiceProvider();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new FoundryHostedAgentSource(null!));
        Assert.Throws<ArgumentNullException>(() => new FoundryHostedAgentSource(null!, ServiceLifetime.Scoped, provider, requireOpenTelemetryAgent: true));
        Assert.Throws<ArgumentNullException>(() => new FoundryHostedAgentSource(_ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped, null!, requireOpenTelemetryAgent: true));
        Assert.Throws<ArgumentOutOfRangeException>(() => new FoundryHostedAgentSource(_ => new TrackingAgent(new AgentLifetimeLog()), (ServiceLifetime)42, provider, requireOpenTelemetryAgent: true));
        await Assert.ThrowsAsync<ArgumentNullException>(() => new FoundryHostedAgentSource(new TrackingAgent(new AgentLifetimeLog())).AcquireAsync(null!).AsTask());
    }

    [Theory]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public async Task AddFoundryResponses_PerRunAgentWithoutOpenTelemetry_FailsAndDisposesTheAgentAsync(ServiceLifetime lifetime)
    {
        // Arrange: the telemetry requirement is on by default.
        var log = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryAgentSessionStore(new TestAgentSessionStore());
        services.AddFoundryResponses(_ => new TrackingAgent(log), lifetime);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(() => DrainAsync(handler));

        // Assert: the agent never ran, it was disposed, and the message says how to fix it.
        Assert.Contains(nameof(FoundryResponsesServerOptions.RequireOpenTelemetryAgent), exception.Message, StringComparison.Ordinal);
        Assert.Contains("UseOpenTelemetry", exception.Message, StringComparison.Ordinal);
        TrackingAgent agent = Assert.Single(log.Created);
        Assert.Equal(0, agent.RunCount);
        Assert.Equal(1, agent.DisposeCount);
    }

    [Theory]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public async Task AddFoundryResponses_PerRunAgentWithOpenTelemetry_IsServedAsync(ServiceLifetime lifetime)
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryAgentSessionStore(new TestAgentSessionStore());
        services.AddFoundryResponses(
            _ => new TrackingAgent(log).AsBuilder().UseOpenTelemetry(sourceName: TelemetrySourceName).Build(),
            lifetime);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler);
        await DrainAsync(handler);

        // Assert
        Assert.Equal(2, log.Created.Count);
        Assert.All(log.Created, agent => Assert.Equal(1, agent.RunCount));
    }

    [Fact]
    public async Task Readiness_PerRunAgentWithoutOpenTelemetry_IsReportedUnhealthyAsync()
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(_ => new TrackingAgent(log), ServiceLifetime.Scoped);
        await using ServiceProvider provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });

        // Act
        HealthReport report = await provider.GetRequiredService<HealthCheckService>().CheckHealthAsync();

        // Assert: the container is not ready, and the agent the probe created was disposed.
        HealthReportEntry entry = report.Entries["foundry-stored-output"];
        Assert.Equal(HealthStatus.Unhealthy, entry.Status);
        Assert.IsType<InvalidOperationException>(entry.Exception);
        Assert.Equal(1, Assert.Single(log.Created).DisposeCount);
    }

    [Fact]
    public async Task BackgroundResponse_ScopedAgent_OutlivesTheHttpRequestAsync()
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var gate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Services.AddFoundryResponses(_ => new TrackingAgent(log, gate), ServiceLifetime.Scoped, LifetimeOnlyOptions());
        builder.Services.AddFoundryAgentSessionStore(_ => new TestAgentSessionStore(), ServiceLifetime.Scoped);
        builder.Services.AddLogging();
        await using WebApplication app = builder.Build();
        app.MapFoundryResponses();
        await app.StartAsync();
        using HttpClient client = ((TestServer)app.Services.GetRequiredService<IServer>()).CreateClient();

        // Act: the POST returns while the agent is still running in the background.
        string body = JsonSerializer.Serialize(new { model = "test", input = "Hello", store = true, background = true });
        using HttpResponseMessage response = await client.PostAsync(
            new Uri("/responses", UriKind.Relative),
            new StringContent(body, Encoding.UTF8, "application/json"));
        response.EnsureSuccessStatusCode();
        TrackingAgent agent = await log.RunStarted.Task.WaitAsync(TimeSpan.FromSeconds(10));
        bool disposedAfterHttpReturned = agent.IsDisposed;
        gate.SetResult();
        await agent.Disposed.Task.WaitAsync(TimeSpan.FromSeconds(10));

        // Assert
        Assert.False(disposedAfterHttpReturned);
        Assert.False(agent.WasDisposedDuringRun);
        Assert.True(agent.IsDisposed);
    }

    private static AgentFrameworkResponseHandler CreateHandler(
        IServiceCollection services,
        Func<IServiceProvider, AIAgent> agentFactory,
        ServiceLifetime lifetime)
    {
        // These tests cover how agents are created and disposed. Their agents bring no telemetry, so the
        // telemetry requirement, which has tests of its own, is turned off.
        ServiceProvider provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        return new(
            provider,
            new FoundryHostedAgentSource(agentFactory, lifetime, provider, requireOpenTelemetryAgent: false),
            NullLogger<AgentFrameworkResponseHandler>.Instance);
    }

    /// <summary>
    /// Options for tests that cover how agents are created and disposed. Their agents bring no telemetry, so
    /// the telemetry requirement, which has tests of its own, is turned off.
    /// </summary>
    private static FoundryResponsesServerOptions LifetimeOnlyOptions() => new() { RequireOpenTelemetryAgent = false };

    private static AgentFrameworkResponseHandler ResolveHandler(IServiceCollection services) =>
        Assert.IsType<AgentFrameworkResponseHandler>(
            services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true })
                .GetRequiredService<ResponseHandler>());

    private static CreateResponse CreateRequest(string? agentName = null)
    {
        var request = agentName is null
            ? new CreateResponse { Model = "test" }
            : new CreateResponse { Model = "test", AgentReference = new AgentReference(agentName) };
        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new
            {
                type = "message",
                id = "msg_1",
                status = "completed",
                role = "user",
                content = new[] { new { type = "input_text", text = "Hello" } },
            },
        });
        return request;
    }

    private static ResponseContext CreateContext()
    {
        var context = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        context.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        context.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());
        return context.Object;
    }

    private static async Task DrainAsync(AgentFrameworkResponseHandler handler, CreateResponse? request = null)
    {
        await foreach (ResponseStreamEvent _ in handler.CreateAsync(request ?? CreateRequest(), CreateContext(), CancellationToken.None))
        {
        }
    }

    private sealed class AgentLifetimeLog
    {
        public ConcurrentQueue<TrackingAgent> Created { get; } = new();

        public TaskCompletionSource<TrackingAgent> RunStarted { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
    }

    /// <summary>A scoped service an agent factory depends on, recording when its scope disposes it.</summary>
    private sealed class ScopedDependency : IDisposable
    {
        public bool IsDisposed { get; private set; }

        public void Dispose() => this.IsDisposed = true;
    }

    /// <summary>An agent that records when it is created, run, and disposed.</summary>
    private sealed class TrackingAgent : AIAgent, IAsyncDisposable
    {
        private readonly AgentLifetimeLog _log;
        private readonly TaskCompletionSource? _gate;
        private readonly string? _name;
        private int _runCount;
        private int _disposeCount;

        public TrackingAgent(AgentLifetimeLog log, TaskCompletionSource? gate = null, string? name = AgentName)
        {
            this._log = log;
            this._gate = gate;
            this._name = name;
            log.Created.Enqueue(this);
        }

        public override string? Name => this._name;

        public int RunCount => this._runCount;

        public int DisposeCount => this._disposeCount;

        public bool IsDisposed { get; private set; }

        public bool WasDisposedDuringRun { get; private set; }

        public TaskCompletionSource Disposed { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public ValueTask DisposeAsync()
        {
            Interlocked.Increment(ref this._disposeCount);
            this.IsDisposed = true;
            this.Disposed.TrySetResult();
            return default;
        }

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            Interlocked.Increment(ref this._runCount);
            this._log.RunStarted.TrySetResult(this);
            if (this._gate is not null)
            {
                await this._gate.Task.WaitAsync(cancellationToken);
            }

            this.WasDisposedDuringRun = this.IsDisposed;
            yield return new AgentResponseUpdate { MessageId = "resp_msg_1", Contents = [new MeaiTextContent("ok")] };
        }

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new TrackingSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement.Clone());

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions,
            CancellationToken cancellationToken = default) =>
            new(new TrackingSession());

        private sealed class TrackingSession : AgentSession;
    }

    /// <summary>A session store that records the storage identity of every agent it serves.</summary>
    private sealed class RecordingSessionStore : AgentSessionStore, IAsyncDisposable
    {
        public ConcurrentQueue<string> Identities { get; } = new();

        public bool IsDisposed => this.DisposeCount > 0;

        public int DisposeCount { get; private set; }

        public ValueTask DisposeAsync()
        {
            this.DisposeCount++;
            return default;
        }

        public override ValueTask<AgentSession?> GetSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            CancellationToken cancellationToken = default)
        {
            this.Identities.Enqueue(FoundryHostingAgent.GetSessionStorageIdentity(agent, allowInstanceId: true));
            return new((AgentSession?)null);
        }

        public override ValueTask SaveSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            AgentSession session,
            CancellationToken cancellationToken = default)
        {
            this.Identities.Enqueue(FoundryHostingAgent.GetSessionStorageIdentity(agent, allowInstanceId: true));
            return default;
        }

        public override ValueTask DeleteSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            CancellationToken cancellationToken = default) =>
            default;
    }
}
