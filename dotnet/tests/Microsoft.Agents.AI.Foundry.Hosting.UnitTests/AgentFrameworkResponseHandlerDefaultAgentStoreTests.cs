// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Responses;
using Azure.AI.AgentServer.Responses.Models;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Moq;
using MeaiTextContent = Microsoft.Extensions.AI.TextContent;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Tests the session-store lookup for requests that are served by the default (non-keyed) <see cref="AIAgent"/>.
/// The registrations mirror what <c>AddAIAgent("billing", ...).WithSessionStore(store).AsDefault()</c> from
/// <c>Microsoft.Agents.AI.Hosting</c> produces, expressed by hand so that this project keeps its current
/// package references.
/// </summary>
public class AgentFrameworkResponseHandlerDefaultAgentStoreTests
{
    private const string DefaultAgentName = "billing";

    [Fact]
    public async Task CreateAsync_NamelessRequest_UsesKeyedStoreOfDefaultAgentAsync()
    {
        // Arrange
        var keyedStore = new RecordingSessionStore();
        var nonKeyedStore = new RecordingSessionStore();
        var handler = CreateHandler(keyedStore, nonKeyedStore);

        // Act
        await RunRequestAsync(handler, requestedAgentName: null);

        // Assert
        Assert.True(keyedStore.WasUsed);
        Assert.False(nonKeyedStore.WasUsed);
    }

    [Fact]
    public async Task CreateAsync_NamedRequestForDefaultAgent_UsesKeyedStoreOfDefaultAgentAsync()
    {
        // Arrange
        var keyedStore = new RecordingSessionStore();
        var nonKeyedStore = new RecordingSessionStore();
        var handler = CreateHandler(keyedStore, nonKeyedStore);

        // Act
        await RunRequestAsync(handler, requestedAgentName: DefaultAgentName);

        // Assert
        Assert.True(keyedStore.WasUsed);
        Assert.False(nonKeyedStore.WasUsed);
    }

    [Fact]
    public async Task CreateAsync_NamelessRequestWithoutKeyedStore_UsesNonKeyedStoreAsync()
    {
        // Arrange
        var nonKeyedStore = new RecordingSessionStore();
        var handler = CreateHandler(keyedStore: null, nonKeyedStore);

        // Act
        await RunRequestAsync(handler, requestedAgentName: null);

        // Assert
        Assert.True(nonKeyedStore.WasUsed);
    }

    [Fact]
    public async Task CreateAsync_UnknownAgentNameFallsBackToDefaultAgent_UsesKeyedStoreOfDefaultAgentAsync()
    {
        // Arrange
        var keyedStore = new RecordingSessionStore();
        var nonKeyedStore = new RecordingSessionStore();
        var handler = CreateHandler(keyedStore, nonKeyedStore);

        // Act
        await RunRequestAsync(handler, requestedAgentName: "missing");

        // Assert
        Assert.True(keyedStore.WasUsed);
        Assert.False(nonKeyedStore.WasUsed);
    }

    [Fact]
    public async Task CreateAsync_NamelessRequestWithoutAnyStore_ThrowsNamingDefaultAgentAsync()
    {
        // Arrange
        var handler = CreateHandler(keyedStore: null, nonKeyedStore: null);

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            () => RunRequestAsync(handler, requestedAgentName: null));

        // Assert
        Assert.Contains($"'{DefaultAgentName}'", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task CreateAsync_NamedRequestForOtherKeyedAgent_UsesThatAgentsStoreAsync()
    {
        // Arrange
        const string OtherAgentName = "support";
        var otherKeyedStore = new RecordingSessionStore();
        var defaultKeyedStore = new RecordingSessionStore();
        var nonKeyedStore = new RecordingSessionStore();

        var services = CreateServices();
        services.AddKeyedSingleton<AIAgent>(OtherAgentName, new NamedTestAgent(OtherAgentName));
        services.AddKeyedSingleton<AgentSessionStore>(OtherAgentName, otherKeyedStore);
        AddAliasedDefaultAgent(services, new NamedTestAgent(DefaultAgentName), DefaultAgentName);
        services.AddKeyedSingleton<AgentSessionStore>(DefaultAgentName, defaultKeyedStore);
        services.AddSingleton<AgentSessionStore>(nonKeyedStore);

        var handler = CreateHandler(services);

        // Act
        await RunRequestAsync(handler, requestedAgentName: OtherAgentName);

        // Assert
        Assert.True(otherKeyedStore.WasUsed);
        Assert.False(defaultKeyedStore.WasUsed);
        Assert.False(nonKeyedStore.WasUsed);
    }

    [Fact]
    public async Task CreateAsync_NamelessRequestWhenDefaultIsNotAlias_UsesNonKeyedStoreAsync()
    {
        // Arrange
        var keyedStore = new RecordingSessionStore();
        var nonKeyedStore = new RecordingSessionStore();

        var services = CreateServices();

        // The non-keyed agent is a separate instance that merely shares the keyed agent's name, so it is not an alias
        // of that registration and the keyed store must stay out of the picture.
        services.AddKeyedSingleton<AIAgent>(DefaultAgentName, new NamedTestAgent(DefaultAgentName));
        services.AddSingleton<AIAgent>(new NamedTestAgent(DefaultAgentName));
        services.AddKeyedSingleton<AgentSessionStore>(DefaultAgentName, keyedStore);
        services.AddSingleton<AgentSessionStore>(nonKeyedStore);

        var handler = CreateHandler(services);

        // Act
        await RunRequestAsync(handler, requestedAgentName: null);

        // Assert
        Assert.True(nonKeyedStore.WasUsed);
        Assert.False(keyedStore.WasUsed);
    }

    [Fact]
    public async Task CreateAsync_NamelessRequestWithUnnamedDefault_UsesNonKeyedStoreAsync()
    {
        // Arrange
        var keyedStore = new RecordingSessionStore();
        var nonKeyedStore = new RecordingSessionStore();

        var services = CreateServices();

        // The alias shape, but the agent carries no name, so there is no key to look a keyed store up under.
        AddAliasedDefaultAgent(services, new NamedTestAgent(name: null), DefaultAgentName);
        services.AddKeyedSingleton<AgentSessionStore>(DefaultAgentName, keyedStore);
        services.AddSingleton<AgentSessionStore>(nonKeyedStore);

        var handler = CreateHandler(services);

        // Act
        await RunRequestAsync(handler, requestedAgentName: null);

        // Assert
        Assert.True(nonKeyedStore.WasUsed);
        Assert.False(keyedStore.WasUsed);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task CreateAsync_NamelessRequestWhenKeyedAgentIsScoped_UsesNonKeyedStoreAsync(bool validateScopes)
    {
        // Arrange
        var keyedStore = new RecordingSessionStore();
        var nonKeyedStore = new RecordingSessionStore();

        var services = CreateServices();

        // The default agent is a raw non-keyed singleton whose name merely collides with an unrelated scoped keyed
        // registration. Under scope validation, resolving that keyed agent from the root provider throws and the alias
        // probe must treat the failure as "not an alias"; without scope validation the resolution succeeds but yields a
        // different instance. Either way the already-resolved default agent serves the request from the non-keyed store.
        services.AddSingleton<AIAgent>(new NamedTestAgent(DefaultAgentName));
        services.AddKeyedScoped<AIAgent>(DefaultAgentName, (_, _) => new NamedTestAgent(DefaultAgentName));
        services.AddKeyedSingleton<AgentSessionStore>(DefaultAgentName, keyedStore);
        services.AddSingleton<AgentSessionStore>(nonKeyedStore);

        var handler = CreateHandler(services, new ServiceProviderOptions { ValidateScopes = validateScopes });

        // Act
        await RunRequestAsync(handler, requestedAgentName: null);

        // Assert
        Assert.True(nonKeyedStore.WasUsed);
        Assert.False(keyedStore.WasUsed);
    }

    [Fact]
    public async Task CreateAsync_NamelessRequestWhenKeyedAgentIsTransient_ResolvesKeyedCandidateOnceAsync()
    {
        // Arrange
        var keyedStore = new RecordingSessionStore();
        var nonKeyedStore = new RecordingSessionStore();
        var keyedResolutions = 0;

        var services = CreateServices();

        // The keyed registration under the default agent's name is a transient that can never be the same instance as
        // the non-keyed singleton default. Once the probe has proven that, the handler must remember it rather than
        // construct a fresh candidate on every request.
        services.AddSingleton<AIAgent>(new NamedTestAgent(DefaultAgentName));
        services.AddKeyedTransient<AIAgent>(DefaultAgentName, (_, _) =>
        {
            keyedResolutions++;
            return new NamedTestAgent(DefaultAgentName);
        });
        services.AddKeyedSingleton<AgentSessionStore>(DefaultAgentName, keyedStore);
        services.AddSingleton<AgentSessionStore>(nonKeyedStore);

        var handler = CreateHandler(services);

        // Act
        await RunRequestAsync(handler, requestedAgentName: null);
        await RunRequestAsync(handler, requestedAgentName: null);

        // Assert
        Assert.Equal(1, keyedResolutions);
        Assert.True(nonKeyedStore.WasUsed);
        Assert.False(keyedStore.WasUsed);
    }

    [Fact]
    public async Task CreateAsync_NamedRequestWhenDefaultAgentIsScoped_UsesKeyedAgentAndStoreAsync()
    {
        // Arrange
        const string OtherAgentName = "support";
        var keyedStore = new RecordingSessionStore();
        var nonKeyedStore = new RecordingSessionStore();

        var services = CreateServices();

        // The named request resolves its keyed agent without ever needing the default agent; the default agent is only
        // consulted to compute the storage identity. A scoped default that cannot be resolved from the root provider
        // must not turn that lookup into the request's error.
        // The keyed agent is registered through a factory on purpose: with an instance descriptor the container serves
        // the non-keyed scoped AIAgent from the root provider without raising the scope violation at all (measured on
        // Microsoft.Extensions.DependencyInjection), which would leave the guard below untested.
        services.AddKeyedSingleton<AIAgent>(OtherAgentName, (_, _) => new NamedTestAgent(OtherAgentName));
        services.AddKeyedSingleton<AgentSessionStore>(OtherAgentName, keyedStore);
        services.AddScoped<AIAgent>(_ => new NamedTestAgent(DefaultAgentName));
        services.AddSingleton<AgentSessionStore>(nonKeyedStore);

        var handler = CreateHandler(services, new ServiceProviderOptions { ValidateScopes = true });

        // Act
        await RunRequestAsync(handler, requestedAgentName: OtherAgentName);

        // Assert
        Assert.True(keyedStore.WasUsed);
        Assert.False(nonKeyedStore.WasUsed);
    }

    [Fact]
    public async Task CreateAsync_NamelessRequestWhenKeyedAgentFactoryThrows_UsesNonKeyedStoreAsync()
    {
        // Arrange
        var keyedStore = new RecordingSessionStore();
        var nonKeyedStore = new RecordingSessionStore();

        var services = CreateServices();

        // Same collision, but the unrelated keyed registration faults when its factory runs. A probe that throws means
        // "not an alias", never a failed request.
        services.AddSingleton<AIAgent>(new NamedTestAgent(DefaultAgentName));
        services.AddKeyedSingleton<AIAgent>(DefaultAgentName, (_, _) => throw new InvalidOperationException("boom"));
        services.AddKeyedSingleton<AgentSessionStore>(DefaultAgentName, keyedStore);
        services.AddSingleton<AgentSessionStore>(nonKeyedStore);

        var handler = CreateHandler(services);

        // Act
        await RunRequestAsync(handler, requestedAgentName: null);

        // Assert
        Assert.True(nonKeyedStore.WasUsed);
        Assert.False(keyedStore.WasUsed);
    }

    private static AgentFrameworkResponseHandler CreateHandler(RecordingSessionStore? keyedStore, RecordingSessionStore? nonKeyedStore)
    {
        var services = CreateServices();

        // The shape AddAIAgent(name, ...).WithSessionStore(store).AsDefault() registers: a keyed agent, a non-keyed
        // agent forwarding to it, a keyed session store, plus whatever non-keyed store the host already had.
        AddAliasedDefaultAgent(services, new NamedTestAgent(DefaultAgentName), DefaultAgentName);
        if (keyedStore is not null)
        {
            services.AddKeyedSingleton<AgentSessionStore>(DefaultAgentName, keyedStore);
        }

        if (nonKeyedStore is not null)
        {
            services.AddSingleton<AgentSessionStore>(nonKeyedStore);
        }

        return CreateHandler(services);
    }

    /// <summary>
    /// Creates a service collection carrying only what the handler itself needs, so each test adds exactly the agent
    /// and session-store registrations its scenario describes.
    /// </summary>
    private static IServiceCollection CreateServices()
    {
        IServiceCollection services = new ServiceCollection();
        services.AddSingleton<ILogger<AgentFrameworkResponseHandler>>(NullLogger<AgentFrameworkResponseHandler>.Instance);
        services.AddSingleton<HostedSessionIsolationKeyProvider>(new FakeHostedSessionIsolationKeyProvider());
        return services;
    }

    /// <summary>
    /// Registers the two descriptors <c>AddAIAgent(key, ...).AsDefault()</c> produces: the keyed agent, and a non-keyed
    /// registration that forwards to it so both resolutions yield the same instance.
    /// </summary>
    private static void AddAliasedDefaultAgent(IServiceCollection services, AIAgent agent, string key)
    {
        services.AddKeyedSingleton(key, agent);
        services.Add(new ServiceDescriptor(typeof(AIAgent), sp => sp.GetRequiredKeyedService<AIAgent>(key), ServiceLifetime.Singleton));
    }

    private static AgentFrameworkResponseHandler CreateHandler(IServiceCollection services, ServiceProviderOptions? options = null)
        => new(services.BuildServiceProvider(options ?? new ServiceProviderOptions()), NullLogger<AgentFrameworkResponseHandler>.Instance);

    private static async Task RunRequestAsync(AgentFrameworkResponseHandler handler, string? requestedAgentName)
    {
        // An empty Model keeps the request genuinely nameless: GetAgentName falls back to Model when no
        // AgentReference is present, so any non-empty value would take the named path instead.
        var request = new CreateResponse { Model = requestedAgentName is null ? "" : "test" };
        if (requestedAgentName is not null)
        {
            request.AgentReference = new AgentReference(requestedAgentName);
        }

        request.Input = BinaryData.FromObjectAsJson(new[]
        {
            new { type = "message", id = "msg_1", status = "completed", role = "user",
                  content = new[] { new { type = "input_text", text = "Hello" } } }
        });

        var mockContext = new Mock<ResponseContext>("resp_" + new string('0', 46)) { CallBase = true };
        mockContext.Setup(x => x.GetHistoryAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<OutputItem>());
        mockContext.Setup(x => x.GetInputItemsAsync(It.IsAny<bool>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(Array.Empty<Item>());

        await foreach (var _ in handler.CreateAsync(request, mockContext.Object, CancellationToken.None))
        {
        }
    }

    /// <summary>
    /// Session store fake that records whether the handler loaded or saved a session through it.
    /// </summary>
    private sealed class RecordingSessionStore : AgentSessionStore
    {
        public bool WasUsed { get; private set; }

        public override ValueTask<AgentSession?> GetSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            CancellationToken cancellationToken = default)
        {
            this.WasUsed = true;
            return new((AgentSession?)null);
        }

        public override ValueTask SaveSessionAsync(
            AIAgent agent,
            AgentSessionStoreKey key,
            AgentSession session,
            CancellationToken cancellationToken = default)
        {
            this.WasUsed = true;
            return default;
        }
    }

    private sealed class NamedTestAgent(string? name) : AIAgent
    {
        public override string? Name => name;

        protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            yield return new AgentResponseUpdate
            {
                MessageId = "resp_msg_1",
                Contents = [new MeaiTextContent("done")]
            };
            await Task.CompletedTask;
        }

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session,
            AgentRunOptions? options,
            CancellationToken cancellationToken = default) =>
            throw new NotImplementedException();

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default) =>
            new(new NamedTestAgentSession());

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            new(JsonDocument.Parse("{}").RootElement);

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            new(new NamedTestAgentSession());
    }

    private sealed class NamedTestAgentSession : AgentSession;
}
