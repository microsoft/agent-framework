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
/// Covers how the response handler resolves agents and session stores per response run, and the
/// <c>AddFoundryResponses</c> overloads that register an agent factory with a DI lifetime.
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
        factoryServices.AddFoundryResponses(
            AgentName,
            _ => new TrackingAgent(new AgentLifetimeLog()),
            lifetime,
            _ => factoryStore);
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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(log), lifetime, _ => new TestAgentSessionStore());
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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(log), ServiceLifetime.Singleton, _ => new TestAgentSessionStore());
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
    public async Task AddFoundryResponses_StoreFactory_CreatesOneStorePerResponseWithTheAgentLifetimeAsync(ServiceLifetime lifetime)
    {
        // Arrange
        var stores = new ConcurrentQueue<RecordingSessionStore>();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(
            AgentName,
            _ => new TrackingAgent(new AgentLifetimeLog()),
            lifetime,
            _ =>
            {
                var store = new RecordingSessionStore();
                stores.Enqueue(store);
                return store;
            });
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act
        await DrainAsync(handler, CreateRequest(AgentName), CreateContext());
        await DrainAsync(handler, CreateRequest(agentName: null), CreateContext());

        // Assert: each run uses one store, which is disposed when the run ends.
        Assert.Equal(2, stores.Count);
        Assert.All(stores, store => Assert.True(store.IsDisposed));
        Assert.All(stores, store => Assert.NotEmpty(store.Identities));
        Assert.All(stores.SelectMany(store => store.Identities), identity => Assert.Equal($"name:{AgentName}", identity));
    }

    [Fact]
    public async Task AddFoundryResponses_SingletonStoreFactory_CreatesOneStoreForTheProcessAsync()
    {
        // Arrange
        var stores = new ConcurrentQueue<RecordingSessionStore>();
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(
            AgentName,
            _ => new TrackingAgent(new AgentLifetimeLog()),
            ServiceLifetime.Singleton,
            _ =>
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
    public async Task AddFoundryResponses_StoreFactoryReturnsNull_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped, _ => null!);
        AgentFrameworkResponseHandler handler = ResolveHandler(services);

        // Act & Assert
        InvalidOperationException exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => DrainAsync(handler, CreateRequest(AgentName), CreateContext()));
        Assert.Contains("session store factory", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AddFoundryResponses_FactoryReturnsNull_ThrowsInvalidOperationExceptionAsync()
    {
        // Arrange
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddFoundryResponses(AgentName, _ => null!, ServiceLifetime.Scoped, _ => new TestAgentSessionStore());
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
    public void AddFoundryResponses_Factory_RegistersOnlyKeyedAgentAndStoreWithTheRequestedLifetime()
    {
        // Arrange
        var services = new ServiceCollection();

        // Act
        services.AddFoundryResponses(
            AgentName,
            _ => new TrackingAgent(new AgentLifetimeLog()),
            ServiceLifetime.Scoped,
            _ => new TestAgentSessionStore());

        // Assert: one registration per created object, so DI owns its disposal once.
        ServiceDescriptor keyed = Assert.Single(services, d => d.ServiceType == typeof(AIAgent));
        Assert.True(keyed.IsKeyedService);
        Assert.Equal(AgentName, keyed.ServiceKey);
        Assert.Equal(ServiceLifetime.Scoped, keyed.Lifetime);
        ServiceDescriptor keyedStore = Assert.Single(services, d => d.ServiceType == typeof(AgentSessionStore) && d.IsKeyedService);
        Assert.Equal(AgentName, keyedStore.ServiceKey);
        Assert.Equal(ServiceLifetime.Scoped, keyedStore.Lifetime);
        Assert.All(
            services.Where(d => d.ServiceType == typeof(AgentSessionStore) && !d.IsKeyedService),
            d => Assert.Equal(ServiceLifetime.Singleton, d.Lifetime));
        FoundryAgentFactoryRegistration marker = Assert.Single(
            services.Where(d => d.ServiceType == typeof(FoundryAgentFactoryRegistration))
                .Select(d => Assert.IsType<FoundryAgentFactoryRegistration>(d.ImplementationInstance)));
        Assert.Equal(AgentName, marker.AgentName);
        Assert.True(marker.IsDefault);
    }

    [Fact]
    public void AddFoundryResponses_FactoryWithoutStoreFactory_RegistersTheKeyedStoreAsSingleton()
    {
        // Arrange
        var services = new ServiceCollection();

        // Act
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped);

        // Assert: without a store factory, the lifetime applies to the agent only.
        ServiceDescriptor keyedStore = Assert.Single(services, d => d.ServiceType == typeof(AgentSessionStore) && d.IsKeyedService);
        Assert.Equal(ServiceLifetime.Singleton, keyedStore.Lifetime);
        Assert.IsType<FoundryAgentSessionStore>(keyedStore.KeyedImplementationInstance);
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
        factoryServices.AddFoundryResponses("first", _ => new TrackingAgent(new AgentLifetimeLog(), name: "first"), lifetime, _ => factoryStore);
        factoryServices.AddFoundryResponses("second", _ => new TrackingAgent(new AgentLifetimeLog(), name: "second"), lifetime, _ => factoryStore);
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
        services.AddFoundryResponses("first", _ => new TrackingAgent(log, name: "first"), ServiceLifetime.Scoped, _ => store);
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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()), ServiceLifetime.Scoped, _ => store);
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
        services.AddFoundryResponses(
            AgentName,
            _ => new TrackingAgent(log),
            lifetime,
            _ =>
            {
                var store = new RecordingSessionStore();
                stores.Enqueue(store);
                return store;
            });
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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(log), ServiceLifetime.Singleton, _ => store);
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
        services.AddFoundryResponses(AgentName, _ => new TrackingAgent(new AgentLifetimeLog()), agentSessionStoreFactory: _ => new TestAgentSessionStore());
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
        Assert.DoesNotContain(services, d => d.ServiceType == typeof(FoundryAgentFactoryRegistration));
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
            ServiceLifetime.Scoped,
            _ => new TestAgentSessionStore());
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
