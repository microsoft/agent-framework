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
    private readonly string _root;

    public FileSystemAgentSessionStoreTests()
    {
        this._root = Path.Combine(Path.GetTempPath(), "fs-session-store-tests-" + Guid.NewGuid().ToString("N"));
    }

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
            // best-effort cleanup
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
    public async Task GetSessionAsync_NoFileOnDisk_ReturnsFreshSessionFromAgentAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent();

        var session = await store.GetSessionAsync(agent, "conv-1");

        Assert.NotNull(session);
        Assert.Equal(1, agent.CreateCalls);
        Assert.Equal(0, agent.DeserializeCalls);
    }

    [Fact]
    public async Task GetSessionAsync_EmptyFileOnDisk_ReturnsFreshSessionAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        Directory.CreateDirectory(store.RootDirectory);
        File.WriteAllText(Path.Combine(store.RootDirectory, "conv-empty.json"), string.Empty);

        var agent = new TestAgent();
        var session = await store.GetSessionAsync(agent, "conv-empty");

        Assert.NotNull(session);
        Assert.Equal(1, agent.CreateCalls);
        Assert.Equal(0, agent.DeserializeCalls);
    }

    [Fact]
    public async Task SaveSessionAsync_CreatesRootDirectoryIfMissingAsync()
    {
        var nested = Path.Combine(this._root, "nested", "deeper");
        var store = new FileSystemAgentSessionStore(nested);
        Assert.False(Directory.Exists(nested));

        var agent = new TestAgent("{\"workflow\":\"x\"}");
        await store.SaveSessionAsync(agent, "conv-2", NewSession());

        Assert.True(Directory.Exists(nested));
        Assert.True(File.Exists(Path.Combine(nested, "conv-2.json")));
    }

    [Fact]
    public async Task SaveSessionAsync_ThenGetSessionAsync_RoundTripsViaAgentSerializerAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent("{\"foo\":42}");

        await store.SaveSessionAsync(agent, "round-trip", NewSession());
        await store.GetSessionAsync(agent, "round-trip");

        Assert.Equal(1, agent.SerializeCalls);
        Assert.Equal(1, agent.DeserializeCalls);
        Assert.NotNull(agent.LastDeserialized);
        Assert.Equal(JsonValueKind.Object, agent.LastDeserialized!.Value.ValueKind);
        Assert.Equal(42, agent.LastDeserialized!.Value.GetProperty("foo").GetInt32());
    }

    [Fact]
    public async Task SaveSessionAsync_TwoAgentsSameConversationId_DoNotCollideAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agentA = new TestAgent("{\"who\":\"a\"}", name: "AgentA");
        var agentB = new TestAgent("{\"who\":\"b\"}", name: "AgentB");

        await store.SaveSessionAsync(agentA, "shared-conv", NewSession());
        await store.SaveSessionAsync(agentB, "shared-conv", NewSession());

        // Agents with distinct Names get distinct subdirectories so neither overwrites the other.
        var pathA = Path.Combine(store.RootDirectory, "AgentA", "shared-conv.json");
        var pathB = Path.Combine(store.RootDirectory, "AgentB", "shared-conv.json");
        Assert.True(File.Exists(pathA));
        Assert.True(File.Exists(pathB));
        Assert.Contains("\"a\"", File.ReadAllText(pathA), StringComparison.Ordinal);
        Assert.Contains("\"b\"", File.ReadAllText(pathB), StringComparison.Ordinal);
    }

    [Fact]
    public async Task SaveSessionAsync_LongConversationId_DoesNotStackOverflowAsync()
    {
        // Sanitize previously used unbounded stackalloc — a long id would crash the
        // process. We deliberately keep the value < typical OS file-name limits
        // (~255 chars) so the file write succeeds but Sanitize is forced past the
        // small-input fast path.
        var store = new FileSystemAgentSessionStore(this._root);
        var conversationId = new string('a', 200);
        var agent = new TestAgent();

        await store.SaveSessionAsync(agent, conversationId, NewSession());

        var files = Directory.GetFiles(store.RootDirectory, "*.json");
        Assert.Single(files);
    }

    [Fact]
    public async Task SaveSessionAsync_SanitizesInvalidPathCharactersAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent();

        // Pick an invalid filename char for the current OS. The set differs by platform
        // (e.g. '?' is invalid on Windows but not on Linux), so we must select dynamically.
        var invalidChars = Path.GetInvalidFileNameChars();
        Assert.NotEmpty(invalidChars);
        char invalid = invalidChars[0];
        // Avoid NUL specifically because some shells/loggers handle it oddly; prefer
        // the next character if available.
        if (invalid == '\0' && invalidChars.Length > 1)
        {
            invalid = invalidChars[1];
        }

        var conversationId = $"id-with{invalid}invalid-chars";

        await store.SaveSessionAsync(agent, conversationId, NewSession());

        var files = Directory.GetFiles(store.RootDirectory, "*.json");
        Assert.Single(files);
        var fileName = Path.GetFileName(files[0]);
        Assert.DoesNotContain(invalid.ToString(), fileName, StringComparison.Ordinal);
        Assert.Contains("id-with", fileName, StringComparison.Ordinal);
        Assert.Contains("invalid-chars", fileName, StringComparison.Ordinal);
    }

    [Fact]
    public async Task SaveSessionAsync_ConcurrentSavesOnSameConversation_DoNotCollideOnTempFileAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent("{\"x\":1}");

        // Fan out N concurrent saves; with a fixed temp filename ("path.tmp") this would
        // race on FileMode.Create / Move. Verify they all complete successfully.
        var tasks = new List<Task>();
        for (int i = 0; i < 16; i++)
        {
            tasks.Add(store.SaveSessionAsync(agent, "concurrent", NewSession()).AsTask());
        }

        await Task.WhenAll(tasks);

        Assert.True(File.Exists(Path.Combine(store.RootDirectory, "concurrent.json")));
        var leftoverTempFiles = Directory.GetFiles(store.RootDirectory, "*.tmp");
        Assert.Empty(leftoverTempFiles);
    }

    [Theory]
    [InlineData(".")]
    [InlineData("..")]
    [InlineData("...")]
    public async Task SaveSessionAsync_AgentNameIsDotSegment_DoesNotEscapeRootAsync(string agentName)
    {
        // Defense-in-depth: Path.GetInvalidFileNameChars() on Linux only contains NUL and '/',
        // so segments composed entirely of dots would otherwise resolve to the parent of root.
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent(name: agentName);

        await store.SaveSessionAsync(agent, "conv-dots", NewSession());

        // The session file must land inside RootDirectory, not in (or above) it as a sibling.
        var allFiles = Directory.GetFiles(store.RootDirectory, "*.json", SearchOption.AllDirectories);
        Assert.Single(allFiles);
        var fullPath = Path.GetFullPath(allFiles[0]);
        Assert.StartsWith(Path.GetFullPath(this._root) + Path.DirectorySeparatorChar, fullPath, StringComparison.Ordinal);

        // The bucket directory name must not be a navigable dot-segment.
        var bucketName = Path.GetFileName(Path.GetDirectoryName(fullPath)!);
        Assert.NotEmpty(bucketName);
        Assert.DoesNotContain(bucketName, c => c == '.');
    }

    private static TestSession NewSession() => new();

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
            return new ValueTask<AgentSession>(NewSession());
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
            return new ValueTask<AgentSession>(NewSession());
        }

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<Extensions.AI.ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<Extensions.AI.ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
    }
}
