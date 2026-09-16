// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Foundry.Hosting;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

public sealed class FileSystemAgentSessionStoreTests : IDisposable
{
    private readonly string _root =
        Path.Combine(Path.GetTempPath(), "fs-session-store-tests-" + Guid.NewGuid().ToString("N"));

    public void Dispose()
    {
        try
        {
            if (Directory.Exists(this._root))
            {
                Directory.Delete(this._root, recursive: true);
            }
        }
        catch
        {
            // Best-effort cleanup.
        }
    }

    [Fact]
    public void Constructor_ResolvesRootDirectoryToFullPath()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        Assert.Equal(Path.GetFullPath(this._root), store.RootDirectory);
    }

    [Fact]
    public void Constructor_NullOrWhitespaceRoot_Throws()
    {
        Assert.Throws<ArgumentNullException>(() => new FileSystemAgentSessionStore(null!));
        Assert.Throws<ArgumentException>(() => new FileSystemAgentSessionStore(""));
        Assert.Throws<ArgumentException>(() => new FileSystemAgentSessionStore("   "));
    }

    [Fact]
    public async Task GetSessionAsync_NoFileOnDisk_ReturnsNullAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent();

        AgentSession? session = await store.GetSessionAsync(agent, new AgentSessionStoreKey("session-1"));

        Assert.Null(session);
        Assert.Equal(0, agent.CreateCalls);
        Assert.Equal(0, agent.DeserializeCalls);
        Assert.False(Directory.Exists(this._root));
    }

    [Fact]
    public async Task GetOrCreateSessionAsync_NoFileOnDisk_ReturnsFreshSessionFromAgentAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent();

        AgentSession session = await store.GetOrCreateSessionAsync(agent, new AgentSessionStoreKey("session-1"));

        Assert.NotNull(session);
        Assert.Equal(1, agent.CreateCalls);
        Assert.Equal(0, agent.DeserializeCalls);
    }

    [Fact]
    public async Task GetSessionAsync_EmptyFileOnDisk_ReturnsNullAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var key = new AgentSessionStoreKey("empty");
        var agent = new TestAgent();
        string agentDirectory = AgentDirectory(store, "name:test-agent");
        Directory.CreateDirectory(agentDirectory);
        File.WriteAllText(SessionPath(store, "name:test-agent", key), string.Empty);

        AgentSession? session = await store.GetSessionAsync(agent, key);

        Assert.Null(session);
        Assert.Equal(0, agent.DeserializeCalls);
    }

    [Fact]
    public async Task SaveSessionAsync_CreatesRootDirectoryAndStableKeyFileAsync()
    {
        var nested = Path.Combine(this._root, "nested", "deeper");
        var store = new FileSystemAgentSessionStore(nested);
        var key = new AgentSessionStoreKey("session-1").WithPartition("tenant", "tenant-1");

        await store.SaveSessionAsync(new TestAgent("{\"workflow\":\"x\"}"), key, NewSession());

        Assert.True(File.Exists(SessionPath(store, "name:test-agent", key)));
    }

    [Fact]
    public async Task SaveSessionAsync_ThenGetSessionAsync_RoundTripsViaAgentSerializerAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent("{\"foo\":42}");
        var key = new AgentSessionStoreKey("round-trip").WithPartition("tenant", "tenant-1");

        await store.SaveSessionAsync(agent, key, NewSession());
        await store.GetSessionAsync(agent, key);

        Assert.Equal(1, agent.SerializeCalls);
        Assert.Equal(1, agent.DeserializeCalls);
        Assert.Equal(42, agent.LastDeserialized!.Value.GetProperty("foo").GetInt32());
    }

    [Fact]
    public async Task SaveSessionAsync_TwoAgentsSameKey_DoNotCollideAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var key = new AgentSessionStoreKey("shared");
        var agentA = new TestAgent("{\"who\":\"a\"}", name: "AgentA");
        var agentB = new TestAgent("{\"who\":\"b\"}", name: "AgentB");

        await store.SaveSessionAsync(agentA, key, NewSession());
        await store.SaveSessionAsync(agentB, key, NewSession());

        string pathA = SessionPath(store, "name:AgentA", key);
        string pathB = SessionPath(store, "name:AgentB", key);
        Assert.Contains("\"a\"", File.ReadAllText(pathA), StringComparison.Ordinal);
        Assert.Contains("\"b\"", File.ReadAllText(pathB), StringComparison.Ordinal);
    }

    [Fact]
    public async Task SaveSessionAsync_ArbitraryIdentifiersDoNotBecomePathSegmentsAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var key = new AgentSessionStoreKey("../../session\0")
            .WithPartition("../tenant", "/rooted/value");

        await store.SaveSessionAsync(new TestAgent(), key, NewSession());

        string file = Assert.Single(Directory.GetFiles(store.RootDirectory, "*.json", SearchOption.AllDirectories));
        Assert.Equal(Path.GetFileName(SessionPath(store, "name:test-agent", key)), Path.GetFileName(file));
        Assert.StartsWith(Path.GetFullPath(this._root) + Path.DirectorySeparatorChar, Path.GetFullPath(file), StringComparison.Ordinal);
    }

    [Fact]
    public async Task SaveSessionAsync_DifferentPartitionsProduceDistinctFilesAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent();
        var aliceKey = new AgentSessionStoreKey("shared").WithPartition("user", "alice");
        var bobKey = new AgentSessionStoreKey("shared").WithPartition("user", "bob");

        await store.SaveSessionAsync(agent, aliceKey, NewSession());
        await store.SaveSessionAsync(agent, bobKey, NewSession());

        Assert.Equal(2, Directory.GetFiles(store.RootDirectory, "*.json", SearchOption.AllDirectories).Length);
    }

    [Fact]
    public async Task GetSessionAsync_DifferentPartition_DoesNotReadStoredSessionAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent("{\"secret\":\"alice-only\"}");
        var aliceKey = new AgentSessionStoreKey("shared").WithPartition("user", "alice");
        var bobKey = new AgentSessionStoreKey("shared").WithPartition("user", "bob");
        await store.SaveSessionAsync(agent, aliceKey, NewSession());

        AgentSession? bobSession = await store.GetSessionAsync(agent, bobKey);

        Assert.Null(bobSession);
        Assert.Equal(0, agent.DeserializeCalls);
    }

    [Fact]
    public async Task SaveSessionAsync_ConcurrentSavesOnSameKey_DoNotCollideOnTempFileAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent("{\"x\":1}");
        var key = new AgentSessionStoreKey("concurrent");
        var tasks = new List<Task>();
        for (int index = 0; index < 16; index++)
        {
            tasks.Add(store.SaveSessionAsync(agent, key, NewSession()).AsTask());
        }

        await Task.WhenAll(tasks);

        Assert.True(File.Exists(SessionPath(store, "name:test-agent", key)));
        Assert.Empty(Directory.GetFiles(store.RootDirectory, "*.tmp", SearchOption.AllDirectories));
    }

    [Theory]
    [InlineData(".")]
    [InlineData("..")]
    [InlineData("...")]
    public async Task SaveSessionAsync_AgentNameIsDotSegment_DoesNotEscapeRootAsync(string agentName)
    {
        var store = new FileSystemAgentSessionStore(this._root);

        await store.SaveSessionAsync(
            new TestAgent(name: agentName),
            new AgentSessionStoreKey("session-1"),
            NewSession());

        string fullPath = Path.GetFullPath(Assert.Single(
            Directory.GetFiles(store.RootDirectory, "*.json", SearchOption.AllDirectories)));
        Assert.StartsWith(Path.GetFullPath(this._root) + Path.DirectorySeparatorChar, fullPath, StringComparison.Ordinal);
        string bucketName = Path.GetFileName(Path.GetDirectoryName(fullPath)!);
        Assert.DoesNotContain(bucketName, value => value == '.');
    }

    [Fact]
    public async Task SaveSessionAsync_DistinctAgentNamesWithInvalidCharacters_DoNotCollideAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var key = new AgentSessionStoreKey("session-1");

        await store.SaveSessionAsync(new TestAgent(name: "foo/bar"), key, NewSession());
        await store.SaveSessionAsync(new TestAgent(name: "foo_bar"), key, NewSession());

        Assert.Equal(2, Directory.GetDirectories(store.RootDirectory).Length);
    }

    [Fact]
    public async Task SaveSessionAsync_UnnamedDirectAgent_ThrowsAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => store.SaveSessionAsync(
                new TestAgent(name: null),
                new AgentSessionStoreKey("session-1"),
                NewSession()).AsTask());
    }

    [Fact]
    public async Task SaveSessionAsync_NonWritableDirectory_ThrowsClearActionableIOExceptionAsync()
    {
        Directory.CreateDirectory(this._root);
        string blockingFile = Path.Combine(this._root, "blocking-file");
        File.WriteAllText(blockingFile, "x");
        var store = new FileSystemAgentSessionStore(Path.Combine(blockingFile, ".checkpoints"));

        IOException exception = await Assert.ThrowsAsync<IOException>(
            () => store.SaveSessionAsync(
                new TestAgent(),
                new AgentSessionStoreKey("session-1"),
                NewSession()).AsTask());

        Assert.Contains("could not be created or written to", exception.Message, StringComparison.Ordinal);
        Assert.Contains(FileSystemAgentSessionStore.SessionDataDirectoryEnvironmentVariable, exception.Message, StringComparison.Ordinal);
        Assert.Contains(FileSystemAgentSessionStore.DefaultHostedSessionDataDirectory, exception.Message, StringComparison.Ordinal);
        Assert.NotNull(exception.InnerException);
    }

    [Fact]
    public void ResolveDefaultRootDirectory_Hosted_RootsUnderHome()
    {
        string root = FileSystemAgentSessionStore.ResolveDefaultRootDirectory(
            isHosted: true,
            homeDirectory: "/home/session",
            currentDirectory: "/some/cwd");

        Assert.Equal(Path.Combine("/home/session", FileSystemAgentSessionStore.LocalCheckpointDirectoryName), root);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("/")]
    public void ResolveDefaultRootDirectory_HostedWithUnusableHome_UsesDefault(string? home)
    {
        string root = FileSystemAgentSessionStore.ResolveDefaultRootDirectory(
            isHosted: true,
            homeDirectory: home,
            currentDirectory: "/some/cwd");

        Assert.Equal(
            Path.Combine(
                FileSystemAgentSessionStore.DefaultHostedSessionDataDirectory,
                FileSystemAgentSessionStore.LocalCheckpointDirectoryName),
            root);
    }

    [Fact]
    public void ResolveDefaultRootDirectory_NotHosted_UsesCurrentDirectory()
    {
        string root = FileSystemAgentSessionStore.ResolveDefaultRootDirectory(
            isHosted: false,
            homeDirectory: "/home/session",
            currentDirectory: "/some/cwd");

        Assert.Equal(Path.Combine("/some/cwd", FileSystemAgentSessionStore.LocalCheckpointDirectoryName), root);
    }

    private static TestSession NewSession() => new();

    private static string AgentDirectory(FileSystemAgentSessionStore store, string identity)
        => Path.Combine(
            store.RootDirectory,
            "a-" + FoundryAgentSessionKeyEncoder.BuildAgentStorageKey(identity));

    private static string SessionPath(
        FileSystemAgentSessionStore store,
        string identity,
        AgentSessionStoreKey key)
        => Path.Combine(
            AgentDirectory(store, identity),
            "k-" + FoundryAgentSessionKeyEncoder.BuildStorageKey(
                FoundryAgentSessionKeyEncoder.BuildLogicalKey(identity, key)) + ".json");

    private sealed class TestSession : AgentSession;

    private sealed class TestAgent : AIAgent
    {
        private readonly string _serializedJson;
        private readonly string? _name;

        public TestAgent(string serializedJson = "{}", string? name = "test-agent")
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
            return new ValueTask<AgentSession>(NewSession());
        }

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
        {
            this.SerializeCalls++;
            using var document = JsonDocument.Parse(this._serializedJson);
            return new ValueTask<JsonElement>(document.RootElement.Clone());
        }

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
        {
            this.DeserializeCalls++;
            this.LastDeserialized = serializedState.Clone();
            return new ValueTask<AgentSession>(NewSession());
        }

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<Extensions.AI.ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<Extensions.AI.ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
    }
}
