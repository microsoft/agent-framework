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

        var session = await store.GetSessionAsync(agent, "conv-1", userId: null);

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
        var session = await store.GetSessionAsync(agent, "conv-empty", userId: null);

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
        await store.SaveSessionAsync(agent, "conv-2", NewSession(), userId: null);

        Assert.True(Directory.Exists(nested));
        Assert.True(File.Exists(Path.Combine(nested, "c-conv-2.json")));
    }

    [Fact]
    public async Task SaveSessionAsync_ThenGetSessionAsync_RoundTripsViaAgentSerializerAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent("{\"foo\":42}");

        await store.SaveSessionAsync(agent, "round-trip", NewSession(), userId: null);
        await store.GetSessionAsync(agent, "round-trip", userId: null);

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

        await store.SaveSessionAsync(agentA, "shared-conv", NewSession(), userId: null);
        await store.SaveSessionAsync(agentB, "shared-conv", NewSession(), userId: null);

        // Agents with distinct Names get distinct subdirectories so neither overwrites the other.
        var pathA = Path.Combine(store.RootDirectory, "a-AgentA", "c-shared-conv.json");
        var pathB = Path.Combine(store.RootDirectory, "a-AgentB", "c-shared-conv.json");
        Assert.True(File.Exists(pathA));
        Assert.True(File.Exists(pathB));
        Assert.Contains("\"a\"", File.ReadAllText(pathA), StringComparison.Ordinal);
        Assert.Contains("\"b\"", File.ReadAllText(pathB), StringComparison.Ordinal);
    }

    [Fact]
    public async Task SaveSessionAsync_LongConversationId_DoesNotStackOverflowAsync()
    {
        // Keep the value < typical OS file-name limits (~255 chars) so the file write
        // succeeds, but long enough to force Sanitize past its small-input fast path.
        var store = new FileSystemAgentSessionStore(this._root);
        var conversationId = new string('a', 200);
        var agent = new TestAgent();

        await store.SaveSessionAsync(agent, conversationId, NewSession(), userId: null);

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

        await store.SaveSessionAsync(agent, conversationId, NewSession(), userId: null);

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
            tasks.Add(store.SaveSessionAsync(agent, "concurrent", NewSession(), userId: null).AsTask());
        }

        await Task.WhenAll(tasks);

        Assert.True(File.Exists(Path.Combine(store.RootDirectory, "c-concurrent.json")));
        var leftoverTempFiles = Directory.GetFiles(store.RootDirectory, "*.tmp");
        Assert.Empty(leftoverTempFiles);
    }

    [Theory]
    [InlineData(".")]
    [InlineData("..")]
    [InlineData("...")]
    public async Task SaveSessionAsync_AgentNameIsDotSegment_DoesNotEscapeRootAsync(string agentName)
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent(name: agentName);

        await store.SaveSessionAsync(agent, "conv-dots", NewSession(), userId: null);

        // The session file must land inside RootDirectory, not in (or above) it as a sibling.
        var allFiles = Directory.GetFiles(store.RootDirectory, "*.json", SearchOption.AllDirectories);
        Assert.Single(allFiles);
        var fullPath = Path.GetFullPath(allFiles[0]);
        Assert.StartsWith(Path.GetFullPath(this._root) + Path.DirectorySeparatorChar, fullPath, StringComparison.Ordinal);

        // The bucket directory name must not be a navigable dot-segment. After
        // percent-encoding every dot in an all-dot segment, names like ".", "..", and
        // "..." become "%2E", "%2E%2E", "%2E%2E%2E" — distinct, OS-neutral filenames.
        var bucketName = Path.GetFileName(Path.GetDirectoryName(fullPath)!);
        Assert.NotEmpty(bucketName);
        Assert.NotEqual(".", bucketName);
        Assert.NotEqual("..", bucketName);
        Assert.DoesNotContain(bucketName, c => c == '.');
    }

    [Fact]
    public async Task SaveSessionAsync_DistinctNamesWithInvalidChars_ProduceDistinctFilesAsync()
    {
        // Percent-encoding must keep otherwise-colliding inputs distinct: under the
        // earlier underscore-substitution scheme, "foo/bar" and "foo_bar" both sanitized
        // to "foo_bar" and would have shared a session bucket on disk.
        var store = new FileSystemAgentSessionStore(this._root);
        var agentSlash = new TestAgent(name: "foo/bar");
        var agentUnderscore = new TestAgent(name: "foo_bar");

        await store.SaveSessionAsync(agentSlash, "conv-1", NewSession(), userId: null);
        await store.SaveSessionAsync(agentUnderscore, "conv-1", NewSession(), userId: null);

        var bucketDirs = Directory.GetDirectories(store.RootDirectory);
        Assert.Equal(2, bucketDirs.Length);
    }

    [Fact]
    public async Task GetSessionAsync_NoExistingFile_DoesNotCreateAgentDirectoryAsync()
    {
        // Read operations must not have side effects on the file system.
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent(name: "agent-with-bucket");

        var session = await store.GetSessionAsync(agent, "missing-id", userId: null);

        Assert.NotNull(session);
        Assert.False(Directory.Exists(this._root), "Read miss must not create the root directory.");
    }

    [Fact]
    public void ResolveDefaultRootDirectory_Hosted_RootsUnderHome()
    {
        // Arrange / Act
        var root = FileSystemAgentSessionStore.ResolveDefaultRootDirectory(
            isHosted: true,
            homeDirectory: "/home/session",
            currentDirectory: "/some/cwd");

        // Assert
        Assert.Equal(
            Path.Combine("/home/session", FileSystemAgentSessionStore.LocalCheckpointDirectoryName),
            root);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public void ResolveDefaultRootDirectory_HostedWithoutHome_UsesDefaultSessionDataDirectory(string? home)
    {
        // Arrange / Act
        var root = FileSystemAgentSessionStore.ResolveDefaultRootDirectory(
            isHosted: true,
            homeDirectory: home,
            currentDirectory: "/some/cwd");

        // Assert: falls back to the spec default ("/home/session"), never the filesystem root.
        Assert.Equal(
            Path.Combine(
                FileSystemAgentSessionStore.DefaultHostedSessionDataDirectory,
                FileSystemAgentSessionStore.LocalCheckpointDirectoryName),
            root);
        Assert.NotEqual("/.checkpoints", root);
    }

    [Fact]
    public void ResolveDefaultRootDirectory_NotHosted_UsesCurrentDirectory()
    {
        // Arrange / Act
        var root = FileSystemAgentSessionStore.ResolveDefaultRootDirectory(
            isHosted: false,
            homeDirectory: "/home/session",
            currentDirectory: "/some/cwd");

        // Assert
        Assert.Equal(
            Path.Combine("/some/cwd", FileSystemAgentSessionStore.LocalCheckpointDirectoryName),
            root);
    }

    [Theory]
    [InlineData("/")]
    public void ResolveDefaultRootDirectory_HostedWithFilesystemRootHome_FallsBackToDefault(string home)
    {
        // Arrange / Act: a filesystem-root HOME (e.g. "/") must NOT root the store at
        // "/.checkpoints", which is read-only in the container and caused issue #6231.
        var root = FileSystemAgentSessionStore.ResolveDefaultRootDirectory(
            isHosted: true,
            homeDirectory: home,
            currentDirectory: "/some/cwd");

        // Assert: falls back to the default session-data directory, never the filesystem root.
        Assert.Equal(
            Path.Combine(
                FileSystemAgentSessionStore.DefaultHostedSessionDataDirectory,
                FileSystemAgentSessionStore.LocalCheckpointDirectoryName),
            root);
        Assert.NotEqual(
            Path.Combine(Path.GetPathRoot(Path.GetFullPath(home))!, FileSystemAgentSessionStore.LocalCheckpointDirectoryName),
            root);
    }

    [Fact]
    public async Task SaveSessionAsync_NonWritableDirectory_ThrowsClearActionableIOExceptionAsync()
    {
        // Arrange: place a file where the store's root directory needs to be created. Creating
        // a directory under an existing file fails with IOException on every OS, standing in for
        // the read-only root filesystem of a Foundry hosted container (issue #6231).
        Directory.CreateDirectory(this._root);
        var blockingFile = Path.Combine(this._root, "blocking-file");
        File.WriteAllText(blockingFile, "x");

        var store = new FileSystemAgentSessionStore(Path.Combine(blockingFile, ".checkpoints"));
        var agent = new TestAgent();

        // Act
        var ex = await Assert.ThrowsAsync<IOException>(
            async () => await store.SaveSessionAsync(agent, "conv-fatal", NewSession(), userId: null));

        // Assert: failure stays fatal but the message is clear and actionable, and the original
        // IO error is preserved as the inner exception.
        Assert.Contains("could not be created or written to", ex.Message, StringComparison.Ordinal);
        Assert.Contains(FileSystemAgentSessionStore.SessionDataDirectoryEnvironmentVariable, ex.Message, StringComparison.Ordinal);
        Assert.Contains(FileSystemAgentSessionStore.DefaultHostedSessionDataDirectory, ex.Message, StringComparison.Ordinal);
        Assert.Contains(store.RootDirectory, ex.Message, StringComparison.Ordinal);
        Assert.NotNull(ex.InnerException);
    }

    [Fact]
    public async Task SaveSessionAsync_WithUserId_NestsUnderPrefixedAgentAndUserAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent("{\"who\":\"alice\"}", name: "Concierge");

        await store.SaveSessionAsync(agent, "conv-1", NewSession(), userId: "alice");

        // Layout: {root}/a-{agent}/u-{userId}/c-{conv}.json
        var expected = Path.Combine(store.RootDirectory, "a-Concierge", "u-alice", "c-conv-1.json");
        Assert.True(File.Exists(expected), $"expected session at {expected}");
    }

    [Fact]
    public async Task SaveSessionAsync_NoUserId_OmitsUserSegmentAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent(name: "Concierge");

        await store.SaveSessionAsync(agent, "conv-1", NewSession(), userId: null);

        // No user id -> the u- layer collapses: {root}/a-{agent}/c-{conv}.json
        var expected = Path.Combine(store.RootDirectory, "a-Concierge", "c-conv-1.json");
        Assert.True(File.Exists(expected), $"expected session at {expected}");
        Assert.Empty(Directory.GetDirectories(Path.Combine(store.RootDirectory, "a-Concierge")));
    }

    [Fact]
    public async Task GetSessionAsync_DifferentUser_DoesNotReadAnotherUsersSessionAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent("{\"secret\":\"alice-only\"}", name: "Concierge");

        // Alice saves under the same conversationId Bob will guess/forge.
        await store.SaveSessionAsync(agent, "shared-conv", NewSession(), userId: "alice");

        // Bob requests the same conversationId. The per-user partition means Bob's path is distinct,
        // so the store returns a fresh session (no leak), not Alice's persisted state.
        var bobSession = await store.GetSessionAsync(agent, "shared-conv", userId: "bob");

        Assert.NotNull(bobSession);
        Assert.Equal(1, agent.CreateCalls);     // fresh session created for Bob
        Assert.Equal(0, agent.DeserializeCalls); // Alice's file never deserialized for Bob
    }

    [Fact]
    public async Task SaveSessionAsync_UserIdEqualToAgentName_StaysDistinctViaPrefixesAsync()
    {
        // Without prefixes, agent "x" + no user could collide with no-agent + user "x". The a-/u-
        // prefixes keep the layers unambiguous.
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent(name: "x");

        await store.SaveSessionAsync(agent, "conv-1", NewSession(), userId: "x");

        var expected = Path.Combine(store.RootDirectory, "a-x", "u-x", "c-conv-1.json");
        Assert.True(File.Exists(expected), $"expected session at {expected}");
    }

    [Theory]
    [InlineData("../../escape")]
    [InlineData("..")]
    [InlineData("user/../../escape")]
    [InlineData("a/b")]
    [InlineData("a\\b")]
    [InlineData(".")]
    public async Task SaveSessionAsync_TraversalUserId_IsRejectedAsync(string userId)
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent(name: "Concierge");

        // A forged user id that is not a single safe path segment is rejected outright (CWE-22),
        // not sanitized — so it can never escape the storage root.
        await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await store.SaveSessionAsync(agent, "conv-1", NewSession(), userId: userId));

        // Nothing was written outside (or inside) the root.
        Assert.False(Directory.Exists(this._root) && Directory.GetFiles(this._root, "*.json", SearchOption.AllDirectories).Length > 0);
    }

    [Fact]
    public async Task SaveSessionAsync_AbsoluteOrRootedUserId_IsRejectedAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent(name: "Concierge");

        var rooted = Path.IsPathRooted("/etc") ? "/etc" : Path.GetFullPath("/etc");
        await Assert.ThrowsAsync<InvalidOperationException>(
            async () => await store.SaveSessionAsync(agent, "conv-1", NewSession(), userId: rooted));
    }

    [Fact]
    public async Task SaveSessionAsync_ThenGetSessionAsync_WithUserId_RoundTripsAsync()
    {
        var store = new FileSystemAgentSessionStore(this._root);
        var agent = new TestAgent("{\"foo\":7}", name: "Concierge");

        await store.SaveSessionAsync(agent, "round-trip", NewSession(), userId: "alice");
        await store.GetSessionAsync(agent, "round-trip", userId: "alice");

        Assert.Equal(1, agent.SerializeCalls);
        Assert.Equal(1, agent.DeserializeCalls);
        Assert.Equal(7, agent.LastDeserialized!.Value.GetProperty("foo").GetInt32());
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
