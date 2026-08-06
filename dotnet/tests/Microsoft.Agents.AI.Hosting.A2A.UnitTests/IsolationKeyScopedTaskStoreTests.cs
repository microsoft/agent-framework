// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading;
using System.Threading.Tasks;
using A2A;
using Moq;

namespace Microsoft.Agents.AI.Hosting.A2A.UnitTests;

/// <summary>
/// Unit tests for the <see cref="IsolationKeyScopedTaskStore"/> class.
/// </summary>
public sealed class IsolationKeyScopedTaskStoreTests
{
    private const string AliceKey = "alice";
    private const string BobKey = "bob";
    private const string TaskId = "task-001";

    /// <summary>
    /// Verifies that GetTaskAsync scopes the task ID with the isolation key.
    /// </summary>
    [Fact]
    public async Task GetTaskAsync_ScopesTaskIdWithIsolationKeyAsync()
    {
        // Arrange
        var innerStore = new Mock<ITaskStore>();
        var keyProvider = CreateKeyProvider(AliceKey);
        var store = new IsolationKeyScopedTaskStore(innerStore.Object, keyProvider, strict: true);

        // Act
        await store.GetTaskAsync(TaskId);

        // Assert
        innerStore.Verify(s => s.GetTaskAsync($"{AliceKey}::{TaskId}", It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verifies that SaveTaskAsync scopes the task ID and the persisted ContextId with the isolation key,
    /// without mutating the caller's task instance.
    /// </summary>
    [Fact]
    public async Task SaveTaskAsync_ScopesTaskIdAndContextIdWithIsolationKeyAsync()
    {
        // Arrange
        var innerStore = new Mock<ITaskStore>();
        var keyProvider = CreateKeyProvider(AliceKey);
        var store = new IsolationKeyScopedTaskStore(innerStore.Object, keyProvider, strict: true);
        var task = new AgentTask { Id = TaskId, ContextId = "ctx-1" };

        // Act
        await store.SaveTaskAsync(TaskId, task);

        // Assert - both the store key and the persisted ContextId are scoped
        innerStore.Verify(s => s.SaveTaskAsync(
            $"{AliceKey}::{TaskId}",
            It.Is<AgentTask>(t => t.ContextId == $"{AliceKey}::ctx-1"),
            It.IsAny<CancellationToken>()), Times.Once);

        // Assert - the caller's instance is untouched
        Assert.Equal("ctx-1", task.ContextId);
    }

    /// <summary>
    /// Verifies that GetTaskAsync strips the isolation key from the returned task's ContextId.
    /// </summary>
    [Fact]
    public async Task GetTaskAsync_UnscopesContextIdOnReadAsync()
    {
        // Arrange
        var innerStore = new InMemoryTaskStore();
        var store = new IsolationKeyScopedTaskStore(innerStore, CreateKeyProvider(AliceKey), strict: true);

        await store.SaveTaskAsync(TaskId, new AgentTask { Id = TaskId, ContextId = "ctx-1" });

        // Act
        var result = await store.GetTaskAsync(TaskId);

        // Assert - the caller observes the bare ContextId
        Assert.NotNull(result);
        Assert.Equal("ctx-1", result.ContextId);
    }

    /// <summary>
    /// Verifies that DeleteTaskAsync scopes the task ID with the isolation key.
    /// </summary>
    [Fact]
    public async Task DeleteTaskAsync_ScopesTaskIdWithIsolationKeyAsync()
    {
        // Arrange
        var innerStore = new Mock<ITaskStore>();
        var keyProvider = CreateKeyProvider(AliceKey);
        var store = new IsolationKeyScopedTaskStore(innerStore.Object, keyProvider, strict: true);

        // Act
        await store.DeleteTaskAsync(TaskId);

        // Assert
        innerStore.Verify(s => s.DeleteTaskAsync($"{AliceKey}::{TaskId}", It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verifies that different isolation keys produce different scoped task IDs,
    /// preventing cross-tenant task access.
    /// </summary>
    [Fact]
    public async Task GetTaskAsync_DifferentTenantsGetDifferentScopedIdsAsync()
    {
        // Arrange
        var innerStore = new InMemoryTaskStore();
        var aliceStore = new IsolationKeyScopedTaskStore(innerStore, CreateKeyProvider(AliceKey), strict: true);
        var bobStore = new IsolationKeyScopedTaskStore(innerStore, CreateKeyProvider(BobKey), strict: true);

        var aliceTask = new AgentTask { Id = TaskId, ContextId = "ctx-1" };

        // Act - Alice saves a task
        await aliceStore.SaveTaskAsync(TaskId, aliceTask);

        // Assert - Alice can read it
        var aliceResult = await aliceStore.GetTaskAsync(TaskId);
        Assert.NotNull(aliceResult);

        // Assert - Bob cannot read it (different isolation key → different scoped ID)
        var bobResult = await bobStore.GetTaskAsync(TaskId);
        Assert.Null(bobResult);
    }

    /// <summary>
    /// Verifies that ListTasksAsync scopes the ContextId filter with the isolation key.
    /// </summary>
    [Fact]
    public async Task ListTasksAsync_ScopesContextIdFilterAsync()
    {
        // Arrange
        var innerStore = new Mock<ITaskStore>();
        innerStore
            .Setup(s => s.ListTasksAsync(It.IsAny<ListTasksRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ListTasksResponse());

        var keyProvider = CreateKeyProvider(AliceKey);
        var store = new IsolationKeyScopedTaskStore(innerStore.Object, keyProvider, strict: true);

        var request = new ListTasksRequest { ContextId = "ctx-1" };

        // Act
        await store.ListTasksAsync(request);

        // Assert - ContextId was scoped with the isolation key
        innerStore.Verify(s => s.ListTasksAsync(
            It.Is<ListTasksRequest>(r => r.ContextId == $"{AliceKey}::ctx-1"),
            It.IsAny<CancellationToken>()), Times.Once);

        // Assert - original request was not mutated
        Assert.Equal("ctx-1", request.ContextId);
    }

    /// <summary>
    /// Verifies that ListTasksAsync does not modify the ContextId filter when it is null.
    /// </summary>
    [Fact]
    public async Task ListTasksAsync_NullContextId_DoesNotScopeFilterAsync()
    {
        // Arrange
        var innerStore = new Mock<ITaskStore>();
        innerStore
            .Setup(s => s.ListTasksAsync(It.IsAny<ListTasksRequest>(), It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ListTasksResponse());

        var keyProvider = CreateKeyProvider(AliceKey);
        var store = new IsolationKeyScopedTaskStore(innerStore.Object, keyProvider, strict: true);

        var request = new ListTasksRequest { ContextId = null };

        // Act
        await store.ListTasksAsync(request);

        // Assert - ContextId was not modified
        innerStore.Verify(s => s.ListTasksAsync(
            It.Is<ListTasksRequest>(r => r.ContextId == null),
            It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verifies that an unfiltered ListTasksAsync only returns tasks belonging to the calling tenant.
    /// </summary>
    [Fact]
    public async Task ListTasksAsync_NoContextIdFilter_ExcludesOtherTenantsTasksAsync()
    {
        // Arrange
        var innerStore = new InMemoryTaskStore();
        var aliceStore = new IsolationKeyScopedTaskStore(innerStore, CreateKeyProvider(AliceKey), strict: true);
        var bobStore = new IsolationKeyScopedTaskStore(innerStore, CreateKeyProvider(BobKey), strict: true);

        await aliceStore.SaveTaskAsync("alice-task", new AgentTask { Id = "alice-task", ContextId = "ctx-1" });
        await bobStore.SaveTaskAsync("bob-task", new AgentTask { Id = "bob-task", ContextId = "ctx-2" });

        // Act - Bob lists without any filter
        var response = await bobStore.ListTasksAsync(new ListTasksRequest());

        // Assert - only Bob's task is returned, with a bare ContextId
        var task = Assert.Single(response.Tasks);
        Assert.Equal("bob-task", task.Id);
        Assert.Equal("ctx-2", task.ContextId);
        Assert.Equal(1, response.PageSize);
    }

    /// <summary>
    /// Verifies that filtering by ContextId returns the caller's own tasks, since the persisted
    /// ContextId is scoped by the same isolation key as the filter.
    /// </summary>
    [Fact]
    public async Task ListTasksAsync_WithContextIdFilter_ReturnsOwnTasksAsync()
    {
        // Arrange
        var innerStore = new InMemoryTaskStore();
        var aliceStore = new IsolationKeyScopedTaskStore(innerStore, CreateKeyProvider(AliceKey), strict: true);
        var bobStore = new IsolationKeyScopedTaskStore(innerStore, CreateKeyProvider(BobKey), strict: true);

        await aliceStore.SaveTaskAsync(TaskId, new AgentTask { Id = TaskId, ContextId = "ctx-1" });

        // Act
        var aliceResponse = await aliceStore.ListTasksAsync(new ListTasksRequest { ContextId = "ctx-1" });
        var bobResponse = await bobStore.ListTasksAsync(new ListTasksRequest { ContextId = "ctx-1" });

        // Assert - Alice sees her task; Bob sees nothing for the same bare context
        var task = Assert.Single(aliceResponse.Tasks);
        Assert.Equal("ctx-1", task.ContextId);
        Assert.Empty(bobResponse.Tasks);
    }

    /// <summary>
    /// Verifies that strict mode throws when the isolation key provider returns null.
    /// </summary>
    [Fact]
    public async Task GetTaskAsync_StrictMode_NullKey_ThrowsAsync()
    {
        // Arrange
        var innerStore = new Mock<ITaskStore>();
        var keyProvider = CreateKeyProvider(null);
        var store = new IsolationKeyScopedTaskStore(innerStore.Object, keyProvider, strict: true);

        // Act & Assert
        await Assert.ThrowsAsync<InvalidOperationException>(() => store.GetTaskAsync(TaskId));
    }

    /// <summary>
    /// Verifies that non-strict mode passes through the bare task ID when the key is null.
    /// </summary>
    [Fact]
    public async Task GetTaskAsync_NonStrictMode_NullKey_PassesThroughAsync()
    {
        // Arrange
        var innerStore = new Mock<ITaskStore>();
        var keyProvider = CreateKeyProvider(null);
        var store = new IsolationKeyScopedTaskStore(innerStore.Object, keyProvider, strict: false);

        // Act
        await store.GetTaskAsync(TaskId);

        // Assert - bare task ID was used (no scoping)
        innerStore.Verify(s => s.GetTaskAsync(TaskId, It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verifies that when no key provider is registered and strict is false,
    /// the bare task ID is passed through.
    /// </summary>
    [Fact]
    public async Task GetTaskAsync_NoKeyProvider_NonStrict_PassesThroughAsync()
    {
        // Arrange
        var innerStore = new Mock<ITaskStore>();
        var store = new IsolationKeyScopedTaskStore(innerStore.Object, keyProvider: null, strict: false);

        // Act
        await store.GetTaskAsync(TaskId);

        // Assert - bare task ID was used
        innerStore.Verify(s => s.GetTaskAsync(TaskId, It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verifies that colons in the isolation key are escaped to prevent ID ambiguity.
    /// </summary>
    [Fact]
    public async Task GetTaskAsync_EscapesColonsInIsolationKeyAsync()
    {
        // Arrange
        var innerStore = new Mock<ITaskStore>();
        var keyProvider = CreateKeyProvider("tenant:sub");
        var store = new IsolationKeyScopedTaskStore(innerStore.Object, keyProvider, strict: true);

        // Act
        await store.GetTaskAsync(TaskId);

        // Assert - colons are escaped
        innerStore.Verify(s => s.GetTaskAsync(@"tenant\:sub::" + TaskId, It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verifies that backslashes in the isolation key are escaped to prevent ID ambiguity.
    /// </summary>
    [Fact]
    public async Task GetTaskAsync_EscapesBackslashesInIsolationKeyAsync()
    {
        // Arrange
        var innerStore = new Mock<ITaskStore>();
        var keyProvider = CreateKeyProvider(@"domain\user");
        var store = new IsolationKeyScopedTaskStore(innerStore.Object, keyProvider, strict: true);

        // Act
        await store.GetTaskAsync(TaskId);

        // Assert - backslashes are escaped
        innerStore.Verify(s => s.GetTaskAsync(@"domain\\user::" + TaskId, It.IsAny<CancellationToken>()), Times.Once);
    }

    /// <summary>
    /// Verifies that the constructor throws when the inner store is null.
    /// </summary>
    [Fact]
    public void Constructor_NullInnerStore_ThrowsArgumentNullException()
    {
        // Act & Assert
        Assert.Throws<ArgumentNullException>(() => new IsolationKeyScopedTaskStore(null!, null, strict: false));
    }

    private static SessionIsolationKeyProvider CreateKeyProvider(string? key)
    {
        var mock = new Mock<SessionIsolationKeyProvider>();
        mock.Setup(p => p.GetSessionIsolationKeyAsync(It.IsAny<CancellationToken>()))
            .ReturnsAsync(key);
        return mock.Object;
    }
}
