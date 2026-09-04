// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Core.Storage;
using Microsoft.Agents.AI.Foundry.Hosting;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

public sealed class FoundryAgentSessionStoreTests
{
    [Fact]
    public async Task SaveSessionAsync_ThenGetSessionAsync_RoundTripsAsync()
    {
        // Arrange
        var backing = new FakeStateStore();
        var store = NewStore(backing);
        var agent = new TestAgent("{\"foo\":7}", name: "Concierge");
        var key = Key("round-trip", "user", "alice");

        // Act
        await store.SaveSessionAsync(agent, key, new TestSession());
        var session = await store.GetSessionAsync(agent, key);

        // Assert
        Assert.NotNull(session);
        Assert.Equal(1, agent.SerializeCalls);
        Assert.Equal(1, agent.DeserializeCalls);
        Assert.Equal(7, agent.LastDeserialized!.Value.GetProperty("foo").GetInt32());
    }

    [Fact]
    public async Task SaveSessionAsync_StoresReadableLogicalKeyAlongsideTheSessionAsync()
    {
        // Arrange
        var backing = new FakeStateStore();
        var store = NewStore(backing);
        var agent = new TestAgent(name: "Concierge");
        var key = Key("conv-1", "user", "alice");

        // Act
        await store.SaveSessionAsync(agent, key, new TestSession());

        // Assert: the item body keeps the readable key so a stored item can be traced back.
        var item = Assert.Single(backing.Items);
        Assert.Equal("\"a14:name:Concierge|s6:conv-1|n4:user|v5:alice\"", item["key"].ToString());
    }

    [Fact]
    public async Task GetSessionAsync_NothingStored_ReturnsNullAsync()
    {
        // Arrange
        var store = NewStore(new FakeStateStore());
        var agent = new TestAgent(name: "Concierge");

        // Act
        var session = await store.GetSessionAsync(agent, Key("conv-1"));

        // Assert
        Assert.Null(session);
        Assert.Equal(0, agent.CreateCalls);
        Assert.Equal(0, agent.DeserializeCalls);
    }

    [Fact]
    public async Task GetOrCreateSessionAsync_NothingStored_ReturnsFreshSessionFromAgentAsync()
    {
        // Arrange
        var store = NewStore(new FakeStateStore());
        var agent = new TestAgent(name: "Concierge");

        // Act
        var session = await store.GetOrCreateSessionAsync(agent, Key("conv-1"));

        // Assert
        Assert.NotNull(session);
        Assert.Equal(1, agent.CreateCalls);
        Assert.Equal(0, agent.DeserializeCalls);
    }

    [Fact]
    public async Task GetSessionAsync_DifferentUser_DoesNotReadAnotherUsersSessionAsync()
    {
        // Arrange: Alice saves under the conversation id Bob will forge.
        var store = NewStore(new FakeStateStore());
        var agent = new TestAgent("{\"secret\":\"alice-only\"}", name: "Concierge");
        await store.SaveSessionAsync(agent, Key("shared-conv", "user", "alice"), new TestSession());

        // Act
        var bobSession = await store.GetSessionAsync(agent, Key("shared-conv", "user", "bob"));

        // Assert
        Assert.Null(bobSession);
        Assert.Equal(0, agent.DeserializeCalls);
    }

    [Fact]
    public async Task GetSessionAsync_DifferentAgent_DoesNotReadAnotherAgentsSessionAsync()
    {
        // Arrange: one container hosts several keyed agents that must not collide on a shared id.
        var backing = new FakeStateStore();
        var store = NewStore(backing);
        var concierge = new TestAgent("{\"owner\":\"concierge\"}", name: "Concierge");
        var researcher = new TestAgent(name: "Researcher");
        var key = Key("shared-conv", "user", "alice");
        await store.SaveSessionAsync(concierge, key, new TestSession());

        // Act
        var otherSession = await store.GetSessionAsync(researcher, key);

        // Assert
        Assert.Null(otherSession);
        Assert.Equal(0, researcher.DeserializeCalls);
    }

    [Fact]
    public async Task GetSessionAsync_DifferentKeyedRegistration_DoesNotReadAnotherAgentsSessionAsync()
    {
        // Arrange: both agents are unnamed, so their keyed DI registrations are the only stable
        // identities that can separate their sessions.
        var backing = new FakeStateStore();
        var store = NewStore(backing);
        var billingLeaf = new TestAgent("{\"owner\":\"billing\"}");
        var support = new TestAgent();
        AIAgent billing = new FoundryHostingAgent(billingLeaf, "key:billing");
        AIAgent hostedSupport = new FoundryHostingAgent(support, "key:support");
        var key = Key("shared-conv", "user", "alice");
        await store.SaveSessionAsync(billing, key, new TestSession());

        // Act
        var supportSession = await store.GetSessionAsync(hostedSupport, key);

        // Assert
        Assert.Null(supportSession);
        Assert.Equal(0, support.DeserializeCalls);
    }

    [Fact]
    public async Task SaveSessionAsync_UnnamedAgent_ThrowsAsync()
    {
        // Arrange
        var store = NewStore(new FakeStateStore());
        var agent = new TestAgent();

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await store.SaveSessionAsync(agent, Key("conv-1", "user", "alice"), new TestSession()));

        // Assert
        Assert.Contains(nameof(AIAgent.Name), exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetSessionAsync_UnnamedAgent_ThrowsAsync()
    {
        // Arrange
        var store = NewStore(new FakeStateStore());
        var agent = new TestAgent();

        // Act
        var exception = await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await store.GetSessionAsync(agent, Key("conv-1", "user", "alice")));

        // Assert
        Assert.Contains(nameof(AIAgent.Name), exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GetStoreAsync_ResolvesTheStoreOnceAcrossManyCallsAsync()
    {
        // Arrange: binding the store costs a round trip, so it must not happen per request.
        var backing = new FakeStateStore();
        var bindCount = 0;
        var store = new FoundryAgentSessionStore(_ =>
        {
            Interlocked.Increment(ref bindCount);
            return Task.FromResult<FoundryStateStore>(backing);
        });
        var agent = new TestAgent(name: "Concierge");

        // Act
        await store.SaveSessionAsync(agent, Key("conv-1"), new TestSession());
        await store.GetSessionAsync(agent, Key("conv-1"));
        await store.GetSessionAsync(agent, Key("conv-2"));

        // Assert
        Assert.Equal(1, bindCount);
    }

    [Fact]
    public async Task GetStoreAsync_FailedBinding_IsRetriedOnTheNextCallAsync()
    {
        // Arrange: a transient failure while binding must not disable the store for the process.
        var backing = new FakeStateStore();
        var attempts = 0;
        var store = new FoundryAgentSessionStore(_ =>
        {
            attempts++;
            return attempts == 1
                ? Task.FromException<FoundryStateStore>(new FoundryStorageApiException(503, "transient"))
                : Task.FromResult<FoundryStateStore>(backing);
        });
        var agent = new TestAgent(name: "Concierge");

        // Act
        await Assert.ThrowsAsync<FoundryStorageApiException>(
            async () => await store.GetSessionAsync(agent, Key("conv-1")));
        var session = await store.GetSessionAsync(agent, Key("conv-1"));

        // Assert
        Assert.Null(session);
        Assert.Equal(2, attempts);
    }

    [Fact]
    public async Task GetStoreAsync_CanceledBinding_IsRetriedOnTheNextCallAsync()
    {
        // Arrange: the shared binding task itself was canceled, rather than one caller choosing to
        // stop waiting for an otherwise healthy shared task.
        var backing = new FakeStateStore();
        var attempts = 0;
        var store = new FoundryAgentSessionStore(_ =>
        {
            attempts++;
            return attempts == 1
                ? Task.FromCanceled<FoundryStateStore>(new CancellationToken(canceled: true))
                : Task.FromResult<FoundryStateStore>(backing);
        });
        var agent = new TestAgent(name: "Concierge");

        // Act
        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            async () => await store.GetSessionAsync(agent, Key("conv-1")));
        var session = await store.GetSessionAsync(agent, Key("conv-1"));

        // Assert
        Assert.Null(session);
        Assert.Equal(2, attempts);
    }

    [Fact]
    public async Task GetStoreAsync_BindingFaultedWithCancellation_IsRetriedOnTheNextCallAsync()
    {
        // Arrange: some async APIs fault with OperationCanceledException instead of returning a
        // canceled task. That completed shared failure must not remain cached.
        var backing = new FakeStateStore();
        var attempts = 0;
        var store = new FoundryAgentSessionStore(_ =>
        {
            attempts++;
            return attempts == 1
                ? Task.FromException<FoundryStateStore>(new OperationCanceledException())
                : Task.FromResult<FoundryStateStore>(backing);
        });
        var agent = new TestAgent(name: "Concierge");

        // Act
        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            async () => await store.GetSessionAsync(agent, Key("conv-1")));
        var session = await store.GetSessionAsync(agent, Key("conv-1"));

        // Assert
        Assert.Null(session);
        Assert.Equal(2, attempts);
    }

    [Fact]
    public async Task GetStoreAsync_CallerCancellation_DoesNotDiscardTheSharedBindingAsync()
    {
        // Arrange
        var backing = new FakeStateStore();
        var binding = new TaskCompletionSource<FoundryStateStore>(TaskCreationOptions.RunContinuationsAsynchronously);
        var attempts = 0;
        var store = new FoundryAgentSessionStore(_ =>
        {
            attempts++;
            return binding.Task;
        });
        var agent = new TestAgent(name: "Concierge");
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();

        // Act
        await Assert.ThrowsAnyAsync<OperationCanceledException>(
            async () => await store.GetSessionAsync(agent, Key("conv-1"), cancellation.Token));
        binding.SetResult(backing);
        var session = await store.GetSessionAsync(agent, Key("conv-1"));

        // Assert
        Assert.Null(session);
        Assert.Equal(1, attempts);
    }

    [Theory]
    [InlineData("name:Concierge", "conv-1", "a14:name:Concierge|s6:conv-1")]
    [InlineData("default", "conv-1", "a7:default|s6:conv-1")]
    public void BuildLogicalKey_UsesLengthPrefixedComponents(
        string agentIdentity,
        string sessionId,
        string expected)
    {
        // Act
        string key = FoundryAgentSessionKeyEncoder.BuildLogicalKey(agentIdentity, Key(sessionId));

        // Assert
        Assert.Equal(expected, key);
    }

    [Fact]
    public void BuildLogicalKey_DelimitersInsideComponents_DoNotCollide()
    {
        // Act
        string first = FoundryAgentSessionKeyEncoder.BuildLogicalKey(
            "name:Concierge",
            Key("x:c-y", "user", "alice"));
        string second = FoundryAgentSessionKeyEncoder.BuildLogicalKey(
            "name:Concierge",
            Key("y", "user", "alice:c-x"));

        // Assert
        Assert.NotEqual(first, second);
        Assert.NotEqual(
            FoundryAgentSessionKeyEncoder.BuildStorageKey(first),
            FoundryAgentSessionKeyEncoder.BuildStorageKey(second));
    }

    [Fact]
    public void BuildItemKey_StaysWithinThePlatformKeyLimitForAnyInput()
    {
        // Arrange
        var logicalKey = FoundryAgentSessionKeyEncoder.BuildLogicalKey(
            $"name:{new string('a', 200)}",
            Key(new string('s', 200), "user", new string('u', 200)));

        // Act
        var itemKey = FoundryAgentSessionKeyEncoder.BuildStorageKey(logicalKey);

        // Assert
        Assert.InRange(itemKey.Length, 1, 128);
    }

    [Fact]
    public void BuildItemKey_IsStableAndDistinctPerLogicalKey()
    {
        // Arrange / Act
        var first = FoundryAgentSessionKeyEncoder.BuildStorageKey("a14:name:Concierge|s6:conv-1|n4:user|v5:alice");
        var same = FoundryAgentSessionKeyEncoder.BuildStorageKey("a14:name:Concierge|s6:conv-1|n4:user|v5:alice");
        var other = FoundryAgentSessionKeyEncoder.BuildStorageKey("a14:name:Concierge|s6:conv-1|n4:user|v3:bob");

        // Assert
        Assert.Equal(first, same);
        Assert.NotEqual(first, other);
    }

    [Fact]
    public void Constructor_NullOrWhitespaceStoreName_Throws()
    {
        // Act / Assert
        Assert.Throws<ArgumentNullException>(() => new FoundryAgentSessionStore(storeName: null!));
        Assert.Throws<ArgumentException>(() => new FoundryAgentSessionStore(storeName: "   "));
    }

    [Fact]
    public void Constructor_WithoutCredential_IsAllowedForTheSdkLocalFallback()
    {
        // Act
        var store = new FoundryAgentSessionStore();

        // Assert
        Assert.Equal(FoundryAgentSessionStore.DefaultStoreName, store.StoreName);
    }

    private static FoundryAgentSessionStore NewStore(FakeStateStore backing)
        => new(_ => Task.FromResult<FoundryStateStore>(backing));

    private static AgentSessionStoreKey Key(
        string sessionId,
        string? partitionName = null,
        string? partitionValue = null)
        => partitionName is null
            ? new AgentSessionStoreKey(sessionId)
            : new AgentSessionStoreKey(sessionId).WithPartition(partitionName, partitionValue!);

    /// <summary>
    /// An in-memory stand-in for the platform state store. <see cref="FoundryStateStore"/> exposes a
    /// protected constructor and virtual members precisely so it can be substituted like this.
    /// </summary>
    private sealed class FakeStateStore : FoundryStateStore
    {
        private readonly ConcurrentDictionary<string, IDictionary<string, BinaryData>> _items = new(StringComparer.Ordinal);

        public IReadOnlyCollection<IDictionary<string, BinaryData>> Items => (IReadOnlyCollection<IDictionary<string, BinaryData>>)this._items.Values;

        public override string Name => FoundryAgentSessionStore.DefaultStoreName;

        public override Task<StateStoreItemRef> SetItemAsync(
            string key,
            IDictionary<string, BinaryData> value,
            IReadOnlyDictionary<string, string>? tags = null,
            string? ifMatch = null,
            bool requireExists = false,
            CancellationToken cancellationToken = default)
        {
            this._items[key] = value;
            return Task.FromResult(AzureAIAgentServerCoreStorageModelFactory.StateStoreItemRef(id: key, key: key, etag: "etag"));
        }

        public override Task<StateStoreItem?> GetItemAsync(string key, CancellationToken cancellationToken = default)
            => Task.FromResult(this._items.TryGetValue(key, out var value)
                ? AzureAIAgentServerCoreStorageModelFactory.StateStoreItem(id: key, key: key, value: value, etag: "etag")
                : null);
    }

    private sealed class TestSession : AgentSession
    {
    }

    private sealed class TestAgent : AIAgent
    {
        private readonly string _serializedJson;
        private readonly string? _name;

        public TestAgent(string serializedJson = "{}", string? name = null)
        {
            this._serializedJson = serializedJson;
            this._name = name;
        }

        public override string? Name => this._name;

        public int CreateCalls { get; private set; }
        public int SerializeCalls { get; private set; }
        public int DeserializeCalls { get; private set; }
        public JsonElement? LastDeserialized { get; private set; }

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
        {
            this.CreateCalls++;
            return new ValueTask<AgentSession>(new TestSession());
        }

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            this.SerializeCalls++;
            using var doc = JsonDocument.Parse(this._serializedJson);
            return new ValueTask<JsonElement>(doc.RootElement.Clone());
        }

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
        {
            this.DeserializeCalls++;
            this.LastDeserialized = serializedState.Clone();
            return new ValueTask<AgentSession>(new TestSession());
        }

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<Extensions.AI.ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<Extensions.AI.ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
    }
}
