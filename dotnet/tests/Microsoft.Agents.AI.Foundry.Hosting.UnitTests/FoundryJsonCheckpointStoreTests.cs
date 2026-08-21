// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.AgentServer.Core.Storage;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.AI.Foundry.UnitTests.Hosting;

public sealed class FoundryJsonCheckpointStoreTests
{
    [Fact]
    public void Constructor_WithoutCredential_IsAllowedForTheSdkLocalFallback()
    {
        // Act
        var store = new FoundryJsonCheckpointStore();

        // Assert
        Assert.Equal(FoundryJsonCheckpointStore.DefaultStoreName, store.StoreName);
    }

    [Fact]
    public async Task CreateCheckpointAsync_ThenRetrieveCheckpointAsync_RoundTripsAsync()
    {
        // Arrange
        var backing = new FakeCheckpointStateStore();
        var store = NewStore(backing);

        // Act
        var key = await store.CreateCheckpointAsync("session-1", Json("{\"step\":3}"));
        var value = await store.RetrieveCheckpointAsync("session-1", key);

        // Assert
        Assert.Equal("session-1", key.SessionId);
        Assert.Equal(3, value.GetProperty("step").GetInt32());
    }

    [Fact]
    public async Task RetrieveIndexAsync_ReturnsCheckpointsInCommitOrderAsync()
    {
        // Arrange
        var store = NewStore(new FakeCheckpointStateStore());

        // Act
        var first = await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var second = await store.CreateCheckpointAsync("session-1", Json("{\"step\":2}"));
        var third = await store.CreateCheckpointAsync("session-1", Json("{\"step\":3}"));
        var index = (await store.RetrieveIndexAsync("session-1")).ToList();

        // Assert: the contract is oldest first, most recently committed last.
        Assert.Equal([first, second, third], index);
    }

    [Fact]
    public async Task RetrieveIndexAsync_UnknownSession_ReturnsEmptyAsync()
    {
        // Arrange
        var store = NewStore(new FakeCheckpointStateStore());

        // Act
        var index = await store.RetrieveIndexAsync("never-written");

        // Assert
        Assert.Empty(index);
    }

    [Fact]
    public async Task RetrieveIndexAsync_WithParent_ReturnsOnlyThatParentsChildrenAsync()
    {
        // Arrange
        var store = NewStore(new FakeCheckpointStateStore());
        var root = await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var childOfRoot = await store.CreateCheckpointAsync("session-1", Json("{\"step\":2}"), parent: root);
        await store.CreateCheckpointAsync("session-1", Json("{\"step\":3}"), parent: childOfRoot);

        // Act
        var index = (await store.RetrieveIndexAsync("session-1", withParent: root)).ToList();

        // Assert
        Assert.Equal([childOfRoot], index);
    }

    [Fact]
    public async Task RetrieveIndexAsync_PartitionsBySessionAsync()
    {
        // Arrange
        var store = NewStore(new FakeCheckpointStateStore());
        var forFirst = await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var forSecond = await store.CreateCheckpointAsync("session-2", Json("{\"step\":1}"));

        // Act
        var firstIndex = (await store.RetrieveIndexAsync("session-1")).ToList();
        var secondIndex = (await store.RetrieveIndexAsync("session-2")).ToList();

        // Assert
        Assert.Equal([forFirst], firstIndex);
        Assert.Equal([forSecond], secondIndex);
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_UnknownCheckpoint_ThrowsAsync()
    {
        // Arrange
        var store = NewStore(new FakeCheckpointStateStore());

        // Act & Assert
        await Assert.ThrowsAsync<KeyNotFoundException>(
            async () => await store.RetrieveCheckpointAsync("session-1", new CheckpointInfo("session-1", "missing")));
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_CheckpointOfAnotherSession_ThrowsAsync()
    {
        // Arrange
        var store = NewStore(new FakeCheckpointStateStore());
        var key = await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));

        // Act & Assert: the item key mixes in the session, so the same checkpoint id does not leak
        // across sessions.
        await Assert.ThrowsAsync<KeyNotFoundException>(
            async () => await store.RetrieveCheckpointAsync("session-2", new CheckpointInfo("session-2", key.CheckpointId)));
    }

    [Fact]
    public async Task CreateCheckpointAsync_LosesTheIndexRace_RetriesAndKeepsBothEntriesAsync()
    {
        // Arrange: the first index write is rejected as if another instance had committed a
        // checkpoint for the same session in between the read and the write.
        var backing = new FakeCheckpointStateStore { FailNextIndexWrites = 1 };
        var store = NewStore(backing);

        // Act
        var first = await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var second = await store.CreateCheckpointAsync("session-1", Json("{\"step\":2}"));
        var index = (await store.RetrieveIndexAsync("session-1")).ToList();

        // Assert
        Assert.Equal([first, second], index);
    }

    [Fact]
    public async Task CreateCheckpointAsync_UsesConditionalWriteOnAnExistingIndexAsync()
    {
        // Arrange
        var backing = new FakeCheckpointStateStore();
        var store = NewStore(backing);

        // Act
        await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        await store.CreateCheckpointAsync("session-1", Json("{\"step\":2}"));

        // Assert: the first index write creates the item, later ones carry the concurrency token.
        Assert.Equal(1, backing.IndexCreateCalls);
        Assert.Equal(["etag-2"], backing.ObservedIndexIfMatch);
    }

    [Fact]
    public async Task GetLatestCheckpointAsync_ReturnsTheMostRecentlyCommittedCheckpointAsync()
    {
        // Arrange
        var store = NewStore(new FakeCheckpointStateStore());
        var manager = CheckpointManager.CreateJson(store);
        await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var last = await store.CreateCheckpointAsync("session-1", Json("{\"step\":2}"));

        // Act
        var latest = await manager.GetLatestCheckpointAsync("session-1");

        // Assert
        Assert.Equal(last, latest);
    }

    [Fact]
    public void BuildCheckpointKey_StaysWithinThePlatformKeyLimit()
    {
        // Arrange
        var longSessionId = new string('s', 4096);
        var longCheckpointId = new string('c', 4096);

        // Act
        var key = FoundryJsonCheckpointStore.BuildCheckpointKey(longSessionId, longCheckpointId);
        var indexKey = FoundryJsonCheckpointStore.BuildIndexKey(longSessionId);

        // Assert
        Assert.True(key.Length <= 128, $"Checkpoint key was {key.Length} characters.");
        Assert.True(indexKey.Length <= 128, $"Index key was {indexKey.Length} characters.");
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_DeletesPredecessorsOfTheResumeTargetAsync()
    {
        // Arrange: a session that ran three supersteps, so it holds three checkpoints.
        var backing = new FakeCheckpointStateStore();
        var store = NewStore(backing);
        var first = await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var second = await store.CreateCheckpointAsync("session-1", Json("{\"step\":2}"), parent: first);
        var third = await store.CreateCheckpointAsync("session-1", Json("{\"step\":3}"), parent: second);

        // Act: resuming reads the latest checkpoint back.
        var resumed = await store.RetrieveCheckpointAsync("session-1", third);

        // Assert: the resumed checkpoint is returned, and it is the only one left.
        Assert.Equal("{\"step\":3}", resumed.GetRawText());
        Assert.Equal([third], (await store.RetrieveIndexAsync("session-1")).ToList());
        Assert.False(backing.Items.ContainsKey(FoundryJsonCheckpointStore.BuildCheckpointKey("session-1", first.CheckpointId)));
        Assert.False(backing.Items.ContainsKey(FoundryJsonCheckpointStore.BuildCheckpointKey("session-1", second.CheckpointId)));
        Assert.True(backing.Items.ContainsKey(FoundryJsonCheckpointStore.BuildCheckpointKey("session-1", third.CheckpointId)));
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_RetainsCheckpointsCommittedAfterTheResumeTargetAsync()
    {
        // Arrange: the third checkpoint models another request committing after this request chose
        // the second checkpoint as its resume target.
        var backing = new FakeCheckpointStateStore();
        var store = NewStore(backing);
        var first = await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var second = await store.CreateCheckpointAsync("session-1", Json("{\"step\":2}"), parent: first);
        var third = await store.CreateCheckpointAsync("session-1", Json("{\"step\":3}"), parent: second);

        // Act
        await store.RetrieveCheckpointAsync("session-1", second);

        // Assert: only predecessors are obsolete. The concurrent request's later checkpoint remains.
        Assert.Equal([second, third], (await store.RetrieveIndexAsync("session-1")).ToList());
        Assert.False(backing.Items.ContainsKey(FoundryJsonCheckpointStore.BuildCheckpointKey("session-1", first.CheckpointId)));
        Assert.True(backing.Items.ContainsKey(FoundryJsonCheckpointStore.BuildCheckpointKey("session-1", second.CheckpointId)));
        Assert.True(backing.Items.ContainsKey(FoundryJsonCheckpointStore.BuildCheckpointKey("session-1", third.CheckpointId)));
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_RetainsEarlierSiblingBranchAsync()
    {
        // Arrange: two branches share the same root, and either branch may still be referenced by a
        // persisted workflow session.
        var backing = new FakeCheckpointStateStore();
        var store = NewStore(backing);
        var root = await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var firstBranch = await store.CreateCheckpointAsync("session-1", Json("{\"branch\":1}"), parent: root);
        var secondBranch = await store.CreateCheckpointAsync("session-1", Json("{\"branch\":2}"), parent: root);

        // Act
        await store.RetrieveCheckpointAsync("session-1", secondBranch);
        JsonElement firstBranchValue = await store.RetrieveCheckpointAsync("session-1", firstBranch);

        // Assert: the shared ancestor is obsolete, but the earlier sibling remains resumable.
        Assert.Equal("{\"branch\":1}", firstBranchValue.GetRawText());
        Assert.Equal([firstBranch, secondBranch], (await store.RetrieveIndexAsync("session-1")).ToList());
        Assert.False(backing.Items.ContainsKey(FoundryJsonCheckpointStore.BuildCheckpointKey("session-1", root.CheckpointId)));
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_ParentlessEntriesStillUseCommitOrderAsync()
    {
        // Arrange: parentless checkpoints provide no branch relationship, so commit order remains
        // the compatibility signal for deciding which earlier entries are obsolete.
        var backing = new FakeCheckpointStateStore();
        var store = NewStore(backing);
        var firstRoot = await store.CreateCheckpointAsync("session-1", Json("{\"root\":1}"));
        var secondRoot = await store.CreateCheckpointAsync("session-1", Json("{\"root\":2}"));

        // Act
        await store.RetrieveCheckpointAsync("session-1", secondRoot);

        // Assert
        Assert.Equal([secondRoot], (await store.RetrieveIndexAsync("session-1")).ToList());
        Assert.False(backing.Items.ContainsKey(FoundryJsonCheckpointStore.BuildCheckpointKey("session-1", firstRoot.CheckpointId)));
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_LegacyEntriesStillUseCommitOrderAsync()
    {
        // Arrange: old indexes did not record parent metadata, so ordering remains the only
        // compatibility signal available for pruning them.
        var backing = new FakeCheckpointStateStore();
        var store = NewStore(backing);
        var first = await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var second = await store.CreateCheckpointAsync("session-1", Json("{\"step\":2}"));
        backing.ReplaceIndexWithLegacyEntries("session-1", first, second);

        // Act
        await store.RetrieveCheckpointAsync("session-1", second);

        // Assert
        Assert.Equal([second], (await store.RetrieveIndexAsync("session-1")).ToList());
        Assert.False(backing.Items.ContainsKey(FoundryJsonCheckpointStore.BuildCheckpointKey("session-1", first.CheckpointId)));
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_LeavesOtherSessionsAloneAsync()
    {
        // Arrange: two sessions, each holding checkpoints of its own.
        var backing = new FakeCheckpointStateStore();
        var store = NewStore(backing);
        var otherFirst = await store.CreateCheckpointAsync("session-2", Json("{\"step\":1}"));
        var otherSecond = await store.CreateCheckpointAsync("session-2", Json("{\"step\":2}"));
        await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var resumeTarget = await store.CreateCheckpointAsync("session-1", Json("{\"step\":2}"));

        // Act
        await store.RetrieveCheckpointAsync("session-1", resumeTarget);

        // Assert: pruning is scoped to the session that resumed.
        Assert.Equal([otherFirst, otherSecond], (await store.RetrieveIndexAsync("session-2")).ToList());
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_PruningFails_StillReturnsTheCheckpointAsync()
    {
        // Arrange: housekeeping is refused, which must not break a conversation that is resuming.
        var backing = new FakeCheckpointStateStore();
        var store = NewStore(backing);
        var first = await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var resumeTarget = await store.CreateCheckpointAsync("session-1", Json("{\"step\":2}"), parent: first);
        backing.FailNextIndexWrites = 1;

        // Act
        var resumed = await store.RetrieveCheckpointAsync("session-1", resumeTarget);

        // Assert
        Assert.Equal("{\"step\":2}", resumed.GetRawText());
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_PruningFailsForARealReason_ReportsItAndStillReturnsTheCheckpointAsync()
    {
        // Arrange: the store refuses the index write for a reason that is not a lost race, which is
        // how a credential or network problem would show up. That must be traceable, because
        // unreported it is how a session's checkpoints silently pile up.
        var backing = new FakeCheckpointStateStore();
        var logs = new RecordingLoggerFactory();
        var store = NewStore(backing, logs);
        var first = await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var resumeTarget = await store.CreateCheckpointAsync("session-1", Json("{\"step\":2}"), parent: first);
        backing.FailNextIndexWritesAuthentically = 1;

        // Act
        var resumed = await store.RetrieveCheckpointAsync("session-1", resumeTarget);

        // Assert: the resume succeeds, and the failure is reported rather than swallowed.
        Assert.Equal("{\"step\":2}", resumed.GetRawText());
        var warning = Assert.Single(logs.Entries, entry => entry.Level == LogLevel.Warning);
        Assert.Contains("session-1", warning.Message, StringComparison.Ordinal);
        Assert.NotNull(warning.Exception);
    }

    [Fact]
    public async Task RetrieveCheckpointAsync_PruningLosesARace_DoesNotWarnAsync()
    {
        // Arrange: losing to another writer is expected under concurrency and is not a problem, so
        // it must not be reported as one.
        var backing = new FakeCheckpointStateStore();
        var logs = new RecordingLoggerFactory();
        var store = NewStore(backing, logs);
        var first = await store.CreateCheckpointAsync("session-1", Json("{\"step\":1}"));
        var resumeTarget = await store.CreateCheckpointAsync("session-1", Json("{\"step\":2}"), parent: first);
        backing.FailNextIndexWrites = 1;

        // Act
        await store.RetrieveCheckpointAsync("session-1", resumeTarget);

        // Assert
        Assert.DoesNotContain(logs.Entries, entry => entry.Level >= LogLevel.Warning);
    }

    [Fact]
    public void BuildCheckpointKey_DifferentSessionsNeverShareAKey()
    {
        // Act
        var first = FoundryJsonCheckpointStore.BuildCheckpointKey("session-1", "abc");
        var second = FoundryJsonCheckpointStore.BuildCheckpointKey("session-2", "abc");

        // Assert
        Assert.NotEqual(first, second);
    }

    private static FoundryJsonCheckpointStore NewStore(FoundryStateStore backing, ILoggerFactory? loggerFactory = null)
        => new(_ => Task.FromResult(backing), loggerFactory: loggerFactory);

    private static JsonElement Json(string json)
    {
        using var document = JsonDocument.Parse(json);
        return document.RootElement.Clone();
    }

    /// <summary>
    /// An in-memory stand-in for the platform store. It models the parts this store depends on:
    /// item bodies keyed by item key, a concurrency token that changes on every write, and the
    /// rejection of a conditional write whose token is stale.
    /// </summary>
    private sealed class FakeCheckpointStateStore : FoundryStateStore
    {
        private int _etagCounter;

        public override string Name => FoundryJsonCheckpointStore.DefaultStoreName;

        /// <summary>How many of the next index writes are rejected as having lost a race.</summary>
        public int FailNextIndexWrites { get; set; }

        /// <summary>
        /// How many of the next index writes are rejected for a reason that is not a lost race,
        /// which is how a credential or network problem would reach this store.
        /// </summary>
        public int FailNextIndexWritesAuthentically { get; set; }

        public int IndexCreateCalls { get; private set; }

        public List<string> ObservedIndexIfMatch { get; } = [];

        public override Task<StateStoreItemRef> CreateItemAsync(
            string key,
            IDictionary<string, BinaryData> value,
            IReadOnlyDictionary<string, string>? tags = null,
            CancellationToken cancellationToken = default)
        {
            if (key.StartsWith("wi-", StringComparison.Ordinal))
            {
                this.IndexCreateCalls++;
            }

            if (this.Items.ContainsKey(key))
            {
                throw new FoundryStorageConflictException("conflict");
            }

            return Task.FromResult(this.Write(key, value));
        }

        public override Task<StateStoreItemRef> SetItemAsync(
            string key,
            IDictionary<string, BinaryData> value,
            IReadOnlyDictionary<string, string>? tags = null,
            string? ifMatch = null,
            bool requireExists = false,
            CancellationToken cancellationToken = default)
        {
            if (key.StartsWith("wi-", StringComparison.Ordinal))
            {
                if (ifMatch is not null)
                {
                    this.ObservedIndexIfMatch.Add(ifMatch);
                }

                if (this.FailNextIndexWrites > 0)
                {
                    this.FailNextIndexWrites--;
                    throw new FoundryStoragePreconditionException("precondition failed");
                }

                if (this.FailNextIndexWritesAuthentically > 0)
                {
                    this.FailNextIndexWritesAuthentically--;
                    throw new FoundryStorageException(503, "service unavailable");
                }
            }

            if (ifMatch is not null && (!this.Items.TryGetValue(key, out var existing) || existing.Etag != ifMatch))
            {
                throw new FoundryStoragePreconditionException("precondition failed");
            }

            return Task.FromResult(this.Write(key, value));
        }

        public override Task<StateStoreItem?> GetItemAsync(string key, CancellationToken cancellationToken = default)
            => Task.FromResult(this.Items.TryGetValue(key, out var entry)
                ? AzureAIAgentServerCoreStorageModelFactory.StateStoreItem(id: key, key: key, value: entry.Value, etag: entry.Etag)
                : null);

        public override Task<DeletedStateStoreItem> DeleteItemAsync(string key, string? ifMatch = null, CancellationToken cancellationToken = default)
        {
            if (!this.Items.TryRemove(key, out _))
            {
                throw new FoundryStorageNotFoundException("not found");
            }

            return Task.FromResult(AzureAIAgentServerCoreStorageModelFactory.DeletedStateStoreItem(id: key, deleted: true));
        }

        /// <summary>The item bodies currently held, so a test can assert what was deleted.</summary>
        public ConcurrentDictionary<string, (IDictionary<string, BinaryData> Value, string Etag)> Items { get; } = new(StringComparer.Ordinal);

        public void ReplaceIndexWithLegacyEntries(string sessionId, params CheckpointInfo[] checkpoints)
        {
            string entriesJson = JsonSerializer.Serialize(
                checkpoints.Select(checkpoint => new Dictionary<string, string>
                {
                    ["id"] = checkpoint.CheckpointId,
                }));

            this.Write(
                FoundryJsonCheckpointStore.BuildIndexKey(sessionId),
                new Dictionary<string, BinaryData>
                {
                    ["session"] = BinaryData.FromString(JsonSerializer.Serialize(sessionId)),
                    ["entries"] = BinaryData.FromString(entriesJson),
                });
        }

        private StateStoreItemRef Write(string key, IDictionary<string, BinaryData> value)
        {
            string etag = string.Create(System.Globalization.CultureInfo.InvariantCulture, $"etag-{++this._etagCounter}");
            this.Items[key] = (value, etag);
            return AzureAIAgentServerCoreStorageModelFactory.StateStoreItemRef(id: key, key: key, etag: etag);
        }
    }

    /// <summary>Captures what the store reported, so a test can assert on it.</summary>
    private sealed class RecordingLoggerFactory : ILoggerFactory
    {
        public List<(LogLevel Level, string Message, Exception? Exception)> Entries { get; } = [];

        public ILogger CreateLogger(string categoryName) => new RecordingLogger(this.Entries);

        public void AddProvider(ILoggerProvider provider)
        {
        }

        public void Dispose()
        {
        }

        private sealed class RecordingLogger(List<(LogLevel Level, string Message, Exception? Exception)> entries) : ILogger
        {
            public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

            public bool IsEnabled(LogLevel logLevel) => true;

            public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
                => entries.Add((logLevel, formatter(state, exception), exception));
        }
    }
}
