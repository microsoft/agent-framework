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
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Covers how the response handler resolves agents and session stores per response run, the
/// <c>AddFoundryResponses</c> overloads that register an agent factory with a DI lifetime, and
/// <c>AddFoundryAgentSessionStore</c>, which registers session stores separately from agents.
/// </summary>
public sealed class FoundryAgentLifetimeTests
{
    private const string AgentName = "lifetime-agent";

    [Fact]
    public async Task CreateAsync_ScopedKeyedAgent_CreatesOnePerResponseAndDisposesItAsync()
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        services.AddKeyedScoped<AIAgent>(AgentName, (_, _) => new TrackingAgent(log));
        AgentFrameworkResponseHandler handler = CreateHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());

        // Assert
        Assert.Equal(2, log.Created.Count);
        Assert.NotSame(log.Created.First(), log.Created.Last());
        Assert.All(log.Created, agent => Assert.True(agent.IsDisposed));
        Assert.All(log.Created, agent => Assert.False(agent.WasDisposedDuringRun));
    }

    [Fact]
    public async Task CreateAsync_TransientKeyedAgent_IsDisposedWhenTheResponseEndsAsync()
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        services.AddKeyedTransient<AIAgent>(AgentName, (_, _) => new TrackingAgent(log));
        AgentFrameworkResponseHandler handler = CreateHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());

        // Assert: the handler only needs the keyed agent, and the root container does not keep it.
        Assert.NotEmpty(log.Created);
        Assert.All(log.Created, agent => Assert.True(agent.IsDisposed));
    }

    [Fact]
    public async Task CreateAsync_SingletonKeyedAgent_IsReusedAndNotDisposedAsync()
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var agent = new TrackingAgent(log);
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        services.AddKeyedSingleton<AIAgent>(AgentName, agent);
        AgentFrameworkResponseHandler handler = CreateHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());

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
        services.AddKeyedScoped<AIAgent>(AgentName, (_, _) => new TrackingAgent(log, gate));
        AgentFrameworkResponseHandler handler = CreateHandler(services);

        // Act
        Task run = Task.Run(() => DrainAsync(handler, CreateRequest(AgentName), CreateContext()));
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
        services.AddKeyedScoped<AIAgent>(AgentName, (_, _) => new TrackingAgent(log));
        AgentFrameworkResponseHandler handler = CreateHandler(services);
        IAsyncEnumerator<ResponseStreamEvent> enumerator = handler
            .CreateAsync(CreateRequest(AgentName), CreateContext(), CancellationToken.None)
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
    public async Task CreateAsync_NamedRequest_CreatesTheRequestedAgentBeforeTheDefaultAgentAsync()
    {
        // Arrange: a keyed agent and an unrelated non-keyed default agent, both created per response.
        var created = new ConcurrentQueue<string>();
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        services.AddKeyedScoped<AIAgent>("named", (_, _) =>
        {
            created.Enqueue("named");
            return new TrackingAgent(new AgentLifetimeLog(), name: "named");
        });
        services.AddScoped<AIAgent>(_ =>
        {
            created.Enqueue("default");
            return new TrackingAgent(new AgentLifetimeLog(), name: "default");
        });
        AgentFrameworkResponseHandler handler = CreateHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest("named"), CreateContext());

        // Assert: the requested agent is resolved first; the default is only consulted afterwards to
        // decide the storage location.
        Assert.Equal(["named", "default"], created.ToArray());
    }

    [Fact]
    public async Task CreateAsync_NamedAgentFactoryThrows_DoesNotCreateTheDefaultAgentAsync()
    {
        // Arrange
        int defaultAgentsCreated = 0;
        var services = new ServiceCollection();
        services.AddSingleton<AgentSessionStore>(new TestAgentSessionStore());
        services.AddKeyedScoped<AIAgent>("named", (_, _) => throw new InvalidOperationException("named agent failed"));
        services.AddScoped<AIAgent>(_ =>
        {
            Interlocked.Increment(ref defaultAgentsCreated);
            return new TrackingAgent(new AgentLifetimeLog(), name: "default");
        });
        AgentFrameworkResponseHandler handler = CreateHandler(services);

        // Act
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => DrainAsync(handler, CreateRequest("named"), CreateContext()));

        // Assert: the failure of the requested agent surfaces without creating the unrelated default agent.
        Assert.Equal("named agent failed", exception.Message);
        Assert.Equal(0, defaultAgentsCreated);
    }

    [Fact]
    public async Task CreateAsync_ScopedKeyedSessionStore_IsCreatedPerResponseAndDisposedAsync()
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var stores = new ConcurrentQueue<RecordingSessionStore>();
        var services = new ServiceCollection();
        services.AddKeyedSingleton<AIAgent>(AgentName, new TrackingAgent(log));
        services.AddKeyedScoped<AgentSessionStore>(AgentName, (_, _) =>
        {
            var store = new RecordingSessionStore();
            stores.Enqueue(store);
            return store;
        });
        AgentFrameworkResponseHandler handler = CreateHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());

        // Assert
        Assert.Equal(2, stores.Count);
        Assert.All(stores, store => Assert.True(store.IsDisposed));
        Assert.All(stores, store => Assert.NotEmpty(store.Identities));
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
        await DrainAsync(instanceHandler, CreateRequest(AgentName), CreateContext());
        string instanceIdentity = Assert.Single(instanceStore.Identities.Distinct());

        var factoryStore = new RecordingSessionStore();
        var factoryServices = new ServiceCollection();
        factoryServices.AddLogging();
        factoryServices.AddFoundryAgentSessionStore(factoryStore);
        factoryServices.AddFoundryResponses(
            AgentName,
            _ => new TrackingAgent(new AgentLifetimeLog()),
            lifetime);
        AgentFrameworkResponseHandler factoryHandler = ResolveHandler(factoryServices);

        // Act: one request names the agent and one does not.
        await DrainAsync(factoryHandler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(factoryHandler, CreateRequest(agentName: null), CreateContext());

        // Assert: every lifetime and both request shapes read and write the same sessions.
        Assert.Equal($"name:{AgentName}", instanceIdentity);
        Assert.All(factoryStore.Identities, identity => Assert.Equal(instanceIdentity, identity));
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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(log), lifetime);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(handler, CreateRequest(agentName: null), CreateContext());

        // Assert: the named and the default registration share one agent within a response run.
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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(log), ServiceLifetime.Singleton);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(handler, CreateRequest(agentName: null), CreateContext());

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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(log));
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
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(handler, CreateRequest(agentName: null), CreateContext());

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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped);
        services.AddFoundryAgentSessionStore(_ =>
        {
            var store = new RecordingSessionStore();
            stores.Enqueue(store);
            return store;
        });
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(handler, CreateRequest(agentName: null), CreateContext());

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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped);
        services.AddFoundryAgentSessionStore(store);
        ServiceProvider provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        var handler = Assert.IsType<AgentFrameworkResponseHandler>(provider.GetRequiredService<ResponseHandler>());

        // Act
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(handler, CreateRequest(agentName: null), CreateContext());
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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped);
        services.AddFoundryAgentSessionStore(_ => null!, ServiceLifetime.Scoped, AgentName);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => DrainAsync(handler, CreateRequest(AgentName), CreateContext()));
        Assert.Contains("session store factory", exception.Message, StringComparison.Ordinal);
        Assert.Contains(AgentName, exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AddFoundryResponses_FactoryReturnsNull_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryAgentSessionStore(new TestAgentSessionStore());
        services.AddFoundryResponses(AgentName, _ => null!, ServiceLifetime.Scoped);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => DrainAsync(handler, CreateRequest(AgentName), CreateContext()));
        Assert.Contains(AgentName, exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void AddFoundryResponses_Factory_InvalidArguments_Throw()
    {
        // Arrange
        var services = new ServiceCollection();

        // Act & Assert
        Assert.Throws<ArgumentException>(() => services.AddFoundryResponses(" ", _ => new TrackingAgent(new AgentLifetimeLog())));
        Assert.Throws<ArgumentNullException>(() => services.AddFoundryResponses(AgentName, null!));
        Assert.Throws<ArgumentOutOfRangeException>(() => services.AddFoundryResponses(
            AgentName,
            _ => new TrackingAgent(new AgentLifetimeLog()),
            (ServiceLifetime)42));
    }

    [Fact]
    public void AddFoundryAgentSessionStore_InvalidArguments_Throw()
    {
        // Arrange
        var services = new ServiceCollection();
        var store = new TestAgentSessionStore();

        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => ((IServiceCollection)null!).AddFoundryAgentSessionStore(store));
        Assert.Throws<ArgumentNullException>(() => services.AddFoundryAgentSessionStore((AgentSessionStore)null!));
        Assert.Throws<ArgumentNullException>(() => services.AddFoundryAgentSessionStore((Func<IServiceProvider, AgentSessionStore>)null!));
        Assert.Throws<ArgumentException>(() => services.AddFoundryAgentSessionStore(store, " "));
        Assert.Throws<ArgumentException>(() => services.AddFoundryAgentSessionStore(_ => store, ServiceLifetime.Singleton, string.Empty));
        Assert.Throws<ArgumentOutOfRangeException>(() => services.AddFoundryAgentSessionStore(_ => store, (ServiceLifetime)42));
        Assert.Throws<ArgumentNullException>(() => ((IHostApplicationBuilder)null!).AddFoundryAgentSessionStore(store));
        Assert.Empty(services);
    }

    [Fact]
    public void AddFoundryResponses_Factory_RegistersOnlyTheKeyedAgentWithTheRequestedLifetime()
    {
        // Arrange
        var services = new ServiceCollection();

        // Act
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped);

        // Assert: one registration per created agent, so DI owns its disposal once, and no store of its own.
        ServiceDescriptor keyed = Assert.Single(services, d => d.ServiceType == typeof(AIAgent));
        Assert.True(keyed.IsKeyedService);
        Assert.Equal(AgentName, keyed.ServiceKey);
        Assert.Equal(ServiceLifetime.Scoped, keyed.Lifetime);
        Assert.DoesNotContain(services, d => d.ServiceType == typeof(AgentSessionStore) && d.IsKeyedService);
        ServiceDescriptor defaultStore = Assert.Single(services, d => d.ServiceType == typeof(AgentSessionStore));
        Assert.Equal(ServiceLifetime.Singleton, defaultStore.Lifetime);
        FoundryDefaultAgentName defaultAgentName = Assert.IsType<FoundryDefaultAgentName>(
            Assert.Single(services, d => d.ServiceType == typeof(FoundryDefaultAgentName)).ImplementationInstance);
        Assert.Equal(AgentName, defaultAgentName.Name);
    }

    [Fact]
    public void AddFoundryResponses_SecondFactoryAgent_IsNotRecordedAsTheDefault()
    {
        // Arrange
        var services = new ServiceCollection();

        // Act
        services.AddFoundryResponses("first", _ => new TrackingAgent(new AgentLifetimeLog(), name: "first"));
        services.AddFoundryResponses("second", _ => new TrackingAgent(new AgentLifetimeLog(), name: "second"));

        // Assert
        FoundryDefaultAgentName defaultAgentName = Assert.IsType<FoundryDefaultAgentName>(
            Assert.Single(services, d => d.ServiceType == typeof(FoundryDefaultAgentName)).ImplementationInstance);
        Assert.Equal("first", defaultAgentName.Name);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void AddFoundryAgentSessionStore_ForAllAgents_ReplacesTheDefaultStoreInAnyOrder(bool registerStoreFirst)
    {
        // Arrange
        var store = new TestAgentSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();

        // Act
        if (registerStoreFirst)
        {
            services.AddFoundryAgentSessionStore(store);
            services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()));
        }
        else
        {
            services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()));
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
        var firstForAgent = new TestAgentSessionStore();
        var secondForAgent = new TestAgentSessionStore();
        var services = new ServiceCollection();

        // Act
        services.AddFoundryAgentSessionStore(first);
        services.AddFoundryAgentSessionStore(firstForAgent, AgentName);
        services.AddFoundryAgentSessionStore(_ => second, ServiceLifetime.Scoped);
        services.AddFoundryAgentSessionStore(secondForAgent, AgentName);
        using ServiceProvider provider = services.BuildServiceProvider();
        using IServiceScope scope = provider.CreateScope();

        // Assert: replacing the store for all agents keeps the store registered for the agent name.
        Assert.Equal(2, services.Count(d => d.ServiceType == typeof(AgentSessionStore)));
        Assert.Same(second, scope.ServiceProvider.GetRequiredService<AgentSessionStore>());
        Assert.Same(secondForAgent, scope.ServiceProvider.GetRequiredKeyedService<AgentSessionStore>(AgentName));
    }

    [Fact]
    public void AddFoundryAgentSessionStore_HostBuilder_RegistersTheStoreWithTheRequestedLifetime()
    {
        // Arrange
        HostApplicationBuilder builder = Host.CreateApplicationBuilder();
        var store = new TestAgentSessionStore();

        // Act
        builder.AddFoundryAgentSessionStore(store);
        builder.AddFoundryAgentSessionStore(_ => new TestAgentSessionStore(), ServiceLifetime.Transient, AgentName);

        // Assert
        ServiceDescriptor forAllAgents = Assert.Single(builder.Services, d => d.ServiceType == typeof(AgentSessionStore) && !d.IsKeyedService);
        Assert.Same(store, forAllAgents.ImplementationInstance);
        ServiceDescriptor forAgent = Assert.Single(builder.Services, d => d.ServiceType == typeof(AgentSessionStore) && d.IsKeyedService);
        Assert.Equal(AgentName, forAgent.ServiceKey);
        Assert.Equal(ServiceLifetime.Transient, forAgent.Lifetime);
    }

    [Fact]
    public async Task AddFoundryAgentSessionStore_ForAgentName_TakesPrecedenceOverTheStoreForAllAgentsAsync()
    {
        // Arrange
        var storeForAll = new RecordingSessionStore();
        var storeForSecond = new RecordingSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses("first", _ => new TrackingAgent(new AgentLifetimeLog(), name: "first"), ServiceLifetime.Scoped);
        services.AddFoundryResponses("second", _ => new TrackingAgent(new AgentLifetimeLog(), name: "second"), ServiceLifetime.Scoped);
        services.AddFoundryAgentSessionStore(storeForAll);
        services.AddFoundryAgentSessionStore(storeForSecond, "second");
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        string firstIdentity = await DrainAndGetIdentityAsync(handler, storeForAll, "first");
        string secondIdentity = await DrainAndGetIdentityAsync(handler, storeForSecond, "second");

        // Assert
        Assert.Equal("name:first", firstIdentity);
        Assert.Equal("key:second", secondIdentity);
        Assert.DoesNotContain("key:second", storeForAll.Identities);
        Assert.DoesNotContain("name:first", storeForSecond.Identities);
    }

    [Fact]
    public async Task AddFoundryAgentSessionStore_ForAgentName_ReplacesTheStorePassedToTheInstanceOverloadAsync()
    {
        // Arrange
        var instanceStore = new RecordingSessionStore();
        var replacement = new RecordingSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog()), instanceStore);
        services.AddFoundryAgentSessionStore(replacement, AgentName);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());

        // Assert
        Assert.Empty(instanceStore.Identities);
        Assert.NotEmpty(replacement.Identities);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task AddFoundryResponses_InstanceWithoutStore_UsesTheStoreForAllAgentsAsync(bool registerStoreFirst)
    {
        // Arrange
        var storeForAll = new RecordingSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();
        if (registerStoreFirst)
        {
            services.AddFoundryAgentSessionStore(storeForAll);
        }

        services.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog()));
        if (!registerStoreFirst)
        {
            services.AddFoundryAgentSessionStore(storeForAll);
        }

        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        string namedIdentity = await DrainAndGetIdentityAsync(handler, storeForAll, AgentName);
        string unnamedIdentity = await DrainAndGetIdentityAsync(handler, storeForAll, agentName: null);

        // Assert
        Assert.Equal($"name:{AgentName}", namedIdentity);
        Assert.Equal(namedIdentity, unnamedIdentity);
    }

    [Fact]
    public async Task AddFoundryResponses_InstanceWithStore_DoesNotShareItsStoreWithOtherAgentsAsync()
    {
        // Arrange: a store passed for one agent, and another agent registered by hand without a store.
        var instanceStore = new RecordingSessionStore();
        var storeForAll = new RecordingSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog(), name: "first"), instanceStore);
        services.AddKeyedSingleton<AIAgent>("other", new TrackingAgent(new AgentLifetimeLog(), name: "other"));
        services.AddFoundryAgentSessionStore(storeForAll);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest("other"), CreateContext());
        await DrainAsync(handler, CreateRequest("first"), CreateContext());

        // Assert
        Assert.Equal("key:other", Assert.Single(storeForAll.Identities.Distinct()));
        Assert.Equal("name:first", Assert.Single(instanceStore.Identities.Distinct()));
    }

    [Fact]
    public void AddFoundryResponses_InstanceWithStore_KeepsTheDefaultStoreForOtherAgents()
    {
        // Arrange
        var instanceStore = new TestAgentSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();

        // Act
        services.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog()), instanceStore);
        using ServiceProvider provider = services.BuildServiceProvider();

        // Assert
        Assert.Same(instanceStore, provider.GetRequiredKeyedService<AgentSessionStore>(AgentName));
        Assert.IsType<FoundryAgentSessionStore>(provider.GetRequiredService<AgentSessionStore>());
    }

    [Fact]
    public async Task CreateAsync_UnknownAgentName_UsesTheDefaultAgentsOwnStoreAsync()
    {
        // Arrange: a request naming no registered agent is answered by the default agent.
        var instanceStore = new RecordingSessionStore();
        var storeForAll = new RecordingSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog()), instanceStore);
        services.AddFoundryAgentSessionStore(storeForAll);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest("unknown"), CreateContext());
        await DrainAsync(handler, CreateRequest(agentName: null), CreateContext());

        // Assert
        Assert.Empty(storeForAll.Identities);
        Assert.Equal($"name:{AgentName}", Assert.Single(instanceStore.Identities.Distinct()));
    }
    [Theory]
    [InlineData(ServiceLifetime.Singleton)]
    [InlineData(ServiceLifetime.Scoped)]
    [InlineData(ServiceLifetime.Transient)]
    public async Task AddFoundryResponses_TwoFactoryAgents_UseTheInstanceOverloadStorageIdentitiesAsync(ServiceLifetime lifetime)
    {
        // Arrange: the instance overload makes the first agent the default and keys the second by name.
        var instanceStore = new RecordingSessionStore();
        var instanceServices = new ServiceCollection();
        instanceServices.AddLogging();
        instanceServices.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog(), name: "first"), instanceStore);
        instanceServices.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog(), name: "second"), instanceStore);
        AgentFrameworkResponseHandler instanceHandler = ResolveHandler(instanceServices);

        var factoryStore = new RecordingSessionStore();
        var factoryServices = new ServiceCollection();
        factoryServices.AddLogging();
        factoryServices.AddFoundryAgentSessionStore(factoryStore);
        factoryServices.AddFoundryResponses("first", _ => new TrackingAgent(new AgentLifetimeLog(), name: "first"), lifetime);
        factoryServices.AddFoundryResponses("second", _ => new TrackingAgent(new AgentLifetimeLog(), name: "second"), lifetime);
        AgentFrameworkResponseHandler factoryHandler = ResolveHandler(factoryServices);

        // Act
        string[] instanceIdentities =
        [
            await DrainAndGetIdentityAsync(instanceHandler, instanceStore, "first"),
            await DrainAndGetIdentityAsync(instanceHandler, instanceStore, "second"),
            await DrainAndGetIdentityAsync(instanceHandler, instanceStore, agentName: null),
        ];
        string[] factoryIdentities =
        [
            await DrainAndGetIdentityAsync(factoryHandler, factoryStore, "first"),
            await DrainAndGetIdentityAsync(factoryHandler, factoryStore, "second"),
            await DrainAndGetIdentityAsync(factoryHandler, factoryStore, agentName: null),
        ];

        // Assert
        Assert.Equal(["name:first", "key:second", "name:first"], instanceIdentities);
        Assert.Equal(instanceIdentities, factoryIdentities);
    }

    [Fact]
    public async Task AddFoundryResponses_FactoryDefaultThenInstanceAgent_KeepsTheFactoryAgentAsDefaultAsync()
    {
        // Arrange: the instance overload must not take over the default slot the factory agent holds.
        var log = new AgentLifetimeLog();
        var store = new RecordingSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryAgentSessionStore(store);
        services.AddFoundryResponses("first", _ => new TrackingAgent(log, name: "first"), ServiceLifetime.Scoped);
        services.AddFoundryResponses(new TrackingAgent(new AgentLifetimeLog(), name: "second"), store);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        string unnamedIdentity = await DrainAndGetIdentityAsync(handler, store, agentName: null);
        string secondIdentity = await DrainAndGetIdentityAsync(handler, store, "second");

        // Assert
        Assert.Equal("name:first", unnamedIdentity);
        Assert.Equal("key:second", secondIdentity);
        Assert.DoesNotContain(services, d => d.ServiceType == typeof(AIAgent) && !d.IsKeyedService);
    }

    [Fact]
    public async Task AddFoundryResponses_NonKeyedAgentRegisteredLater_DoesNotShareTheFactoryAgentSessionsAsync()
    {
        // Arrange: a different agent with the same name is registered as the non-keyed default after the
        // factory overload, so it receives requests without an agent name.
        var store = new RecordingSessionStore();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddSingleton<AgentSessionStore>(store);
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped);
        services.AddSingleton<AIAgent>(new TrackingAgent(new AgentLifetimeLog()));
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        string factoryIdentity = await DrainAndGetIdentityAsync(handler, store, AgentName);
        string nonKeyedIdentity = await DrainAndGetIdentityAsync(handler, store, agentName: null);

        // Assert: the two agents never read or write each other's sessions.
        Assert.Equal($"key:{AgentName}", factoryIdentity);
        Assert.Equal($"name:{AgentName}", nonKeyedIdentity);
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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(log), lifetime);
        services.AddFoundryAgentSessionStore(
            _ =>
            {
                var store = new RecordingSessionStore();
                stores.Enqueue(store);
                return store;
            },
            lifetime,
            AgentName);
        ServiceProvider provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        var handler = Assert.IsType<AgentFrameworkResponseHandler>(provider.GetRequiredService<ResponseHandler>());

        // Act: a named request, an unnamed request, and the readiness enumeration of all agents.
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(handler, CreateRequest(agentName: null), CreateContext());
        await using (AsyncServiceScope scope = provider.CreateAsyncScope())
        {
            Assert.Single(ServiceCollectionExtensions.ResolveRegisteredAgents(scope.ServiceProvider));
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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(log), ServiceLifetime.Singleton);
        services.AddFoundryAgentSessionStore(_ => store);
        ServiceProvider provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        var handler = Assert.IsType<AgentFrameworkResponseHandler>(provider.GetRequiredService<ResponseHandler>());

        // Act
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(handler, CreateRequest(agentName: null), CreateContext());
        bool disposedBeforeShutdown = store.IsDisposed || log.Created.Any(agent => agent.IsDisposed);
        await provider.DisposeAsync();

        // Assert
        Assert.False(disposedBeforeShutdown);
        Assert.Equal(1, Assert.Single(log.Created).DisposeCount);
        Assert.Equal(1, store.DisposeCount);
    }

    [Fact]
    public async Task AddFoundryResponses_ExistingScopedKeyedAgent_IsNotCapturedBySingletonDefaultAsync()
    {
        // Arrange: the caller already registered a scoped agent under the name; the factory call uses
        // the default singleton lifetime.
        var log = new AgentLifetimeLog();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddKeyedScoped<AIAgent>(AgentName, (_, _) => new TrackingAgent(log));
        services.AddFoundryAgentSessionStore(new TestAgentSessionStore());
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()));
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());

        // Assert: the existing scoped registration is used per run and nothing forwards to it.
        Assert.DoesNotContain(services, d => d.ServiceType == typeof(AIAgent) && !d.IsKeyedService);
        Assert.Equal(2, log.Created.Count);
        Assert.All(log.Created, agent => Assert.Equal(1, agent.DisposeCount));
    }

    [Fact]
    public void AddFoundryResponses_Factory_KeepsAnExistingKeyedRegistration()
    {
        // Arrange
        var existing = new TrackingAgent(new AgentLifetimeLog());
        var services = new ServiceCollection();
        services.AddKeyedSingleton<AIAgent>(AgentName, existing);

        // Act
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped);

        // Assert: the existing registration wins, like the instance overload's TryAdd behavior.
        ServiceDescriptor keyed = Assert.Single(services, d => d.ServiceType == typeof(AIAgent) && d.IsKeyedService);
        Assert.Same(existing, keyed.KeyedImplementationInstance);
        Assert.DoesNotContain(services, d => d.ServiceType == typeof(FoundryDefaultAgentName));
    }

    [Fact]
    public void AddFoundryResponses_HostBuilderFactory_RegistersAgentWithTheRequestedLifetime()
    {
        // Arrange
        HostApplicationBuilder builder = Host.CreateApplicationBuilder();

        // Act
        builder.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Transient);
        using ServiceProvider provider = builder.Services.BuildServiceProvider();

        // Assert
        ServiceDescriptor keyed = Assert.Single(builder.Services, d => d.ServiceType == typeof(AIAgent) && d.IsKeyedService);
        Assert.Equal(ServiceLifetime.Transient, keyed.Lifetime);
        Assert.IsType<AgentFrameworkResponseHandler>(provider.GetRequiredService<ResponseHandler>());
    }

    [Fact]
    public async Task BackgroundResponse_ScopedAgent_OutlivesTheHttpRequestAsync()
    {
        // Arrange
        var log = new AgentLifetimeLog();
        var gate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();
        builder.Services.AddFoundryResponses(
            AgentName,
            _ => new TrackingAgent(log, gate),
            ServiceLifetime.Scoped);
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

    private static AgentFrameworkResponseHandler CreateHandler(IServiceCollection services) =>
        new(
            services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true }),
            NullLogger<AgentFrameworkResponseHandler>.Instance);

    private static AgentFrameworkResponseHandler ResolveHandler(IServiceCollection services) =>
        Assert.IsType<AgentFrameworkResponseHandler>(
            services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true })
                .GetRequiredService<ResponseHandler>());

    private static CreateResponse CreateRequest(string? agentName)
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

    private static async Task DrainAsync(AgentFrameworkResponseHandler handler, CreateResponse request, ResponseContext context)
    {
        await foreach (ResponseStreamEvent _ in handler.CreateAsync(request, context, CancellationToken.None))
        {
        }
    }

    /// <summary>Runs one request and returns the single storage identity the store saw during it.</summary>
    private static async Task<string> DrainAndGetIdentityAsync(
        AgentFrameworkResponseHandler handler,
        RecordingSessionStore store,
        string? agentName)
    {
        int before = store.Identities.Count;
        await DrainAsync(handler, CreateRequest(agentName), CreateContext());
        return Assert.Single(store.Identities.Skip(before).Distinct());
    }

    private sealed class AgentLifetimeLog
    {
        public ConcurrentQueue<TrackingAgent> Created { get; } = new();

        public TaskCompletionSource<TrackingAgent> RunStarted { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);
    }

    /// <summary>An agent that records when it is created, run, and disposed.</summary>
    private sealed class TrackingAgent : AIAgent, IAsyncDisposable
    {
        private readonly AgentLifetimeLog _log;
        private readonly TaskCompletionSource? _gate;
        private readonly string _name;
        private int _runCount;
        private int _disposeCount;

        public TrackingAgent(AgentLifetimeLog log, TaskCompletionSource? gate = null, string name = AgentName)
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
