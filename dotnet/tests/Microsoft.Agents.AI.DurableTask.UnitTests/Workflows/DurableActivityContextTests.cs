// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;

namespace Microsoft.Agents.AI.DurableTask.UnitTests.Workflows;

public sealed class DurableActivityContextTests
{
    private static FunctionExecutor<string> CreateTestExecutor(string id = "test-executor")
        => new(id, (_, _, _) => default);

    #region ReadStateAsync

    [Fact]
    public async Task ReadStateAsync_KeyExistsInInitialState_ReturnsValue()
    {
        // Arrange
        Dictionary<string, string> state = new() { ["__default__:counter"] = "42" };
        DurableActivityContext context = new(state, CreateTestExecutor());

        // Act
        int? result = await context.ReadStateAsync<int>("counter");

        // Assert
        Assert.Equal(42, result);
    }

    [Fact]
    public async Task ReadStateAsync_KeyDoesNotExist_ReturnsNull()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act
        string? result = await context.ReadStateAsync<string>("missing");

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task ReadStateAsync_LocalUpdateTakesPriorityOverInitialState()
    {
        // Arrange
        Dictionary<string, string> state = new() { ["__default__:key"] = "\"old\"" };
        DurableActivityContext context = new(state, CreateTestExecutor());
        await context.QueueStateUpdateAsync("key", "new");

        // Act
        string? result = await context.ReadStateAsync<string>("key");

        // Assert
        Assert.Equal("new", result);
    }

    [Fact]
    public async Task ReadStateAsync_ScopeCleared_IgnoresInitialState()
    {
        // Arrange
        Dictionary<string, string> state = new() { ["__default__:key"] = "\"value\"" };
        DurableActivityContext context = new(state, CreateTestExecutor());
        await context.QueueClearScopeAsync();

        // Act
        string? result = await context.ReadStateAsync<string>("key");

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public async Task ReadStateAsync_WithNamedScope_ReadsFromCorrectScope()
    {
        // Arrange
        Dictionary<string, string> state = new()
        {
            ["scopeA:key"] = "\"fromA\"",
            ["scopeB:key"] = "\"fromB\""
        };
        DurableActivityContext context = new(state, CreateTestExecutor());

        // Act
        string? resultA = await context.ReadStateAsync<string>("key", "scopeA");
        string? resultB = await context.ReadStateAsync<string>("key", "scopeB");

        // Assert
        Assert.Equal("fromA", resultA);
        Assert.Equal("fromB", resultB);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    public async Task ReadStateAsync_NullOrEmptyKey_ThrowsArgumentException(string? key)
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(() => context.ReadStateAsync<string>(key!).AsTask());
    }

    #endregion

    #region ReadOrInitStateAsync

    [Fact]
    public async Task ReadOrInitStateAsync_KeyDoesNotExist_CallsFactoryAndQueuesUpdate()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act
        string result = await context.ReadOrInitStateAsync("key", () => "initialized");

        // Assert
        Assert.Equal("initialized", result);
        Assert.True(context.StateUpdates.ContainsKey("__default__:key"));
    }

    [Fact]
    public async Task ReadOrInitStateAsync_KeyExists_ReturnsExistingValue()
    {
        // Arrange
        Dictionary<string, string> state = new() { ["__default__:key"] = "\"existing\"" };
        DurableActivityContext context = new(state, CreateTestExecutor());
        bool factoryCalled = false;

        // Act
        string result = await context.ReadOrInitStateAsync("key", () =>
        {
            factoryCalled = true;
            return "should-not-be-used";
        });

        // Assert
        Assert.Equal("existing", result);
        Assert.False(factoryCalled);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    public async Task ReadOrInitStateAsync_NullOrEmptyKey_ThrowsArgumentException(string? key)
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(
            () => context.ReadOrInitStateAsync(key!, () => "value").AsTask());
    }

    [Fact]
    public async Task ReadOrInitStateAsync_ValueType_MissingKey_CallsFactory()
    {
        // Arrange
        // Validates that ReadStateAsync<int> returns null (not 0) for missing keys,
        // because the return type is int? (Nullable<int>). This ensures the factory
        // is correctly invoked for value types when the key does not exist.
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act
        int result = await context.ReadOrInitStateAsync("counter", () => 42);

        // Assert
        Assert.Equal(42, result);
        Assert.True(context.StateUpdates.ContainsKey("__default__:counter"));
    }

    [Fact]
    public async Task ReadOrInitStateAsync_NullFactory_ThrowsArgumentNullException()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act & Assert
        await Assert.ThrowsAsync<ArgumentNullException>(
            () => context.ReadOrInitStateAsync<string>("key", null!).AsTask());
    }

    #endregion

    #region QueueStateUpdateAsync

    [Fact]
    public async Task QueueStateUpdateAsync_SetsValue_VisibleToSubsequentRead()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act
        await context.QueueStateUpdateAsync("key", "hello");
        string? result = await context.ReadStateAsync<string>("key");

        // Assert
        Assert.Equal("hello", result);
    }

    [Fact]
    public async Task QueueStateUpdateAsync_NullValue_RecordsDeletion()
    {
        // Arrange
        Dictionary<string, string> state = new() { ["__default__:key"] = "\"value\"" };
        DurableActivityContext context = new(state, CreateTestExecutor());

        // Act
        await context.QueueStateUpdateAsync<string>("key", null);

        // Assert
        Assert.True(context.StateUpdates.ContainsKey("__default__:key"));
        Assert.Null(context.StateUpdates["__default__:key"]);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    public async Task QueueStateUpdateAsync_NullOrEmptyKey_ThrowsArgumentException(string? key)
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act & Assert
        await Assert.ThrowsAnyAsync<ArgumentException>(
            () => context.QueueStateUpdateAsync(key!, "value").AsTask());
    }

    #endregion

    #region QueueClearScopeAsync

    [Fact]
    public async Task QueueClearScopeAsync_DefaultScope_ClearsStateAndPendingUpdates()
    {
        // Arrange
        Dictionary<string, string> state = new() { ["__default__:key"] = "\"value\"" };
        DurableActivityContext context = new(state, CreateTestExecutor());
        await context.QueueStateUpdateAsync("pending", "data");

        // Act
        await context.QueueClearScopeAsync();

        // Assert
        Assert.Contains("__default__", context.ClearedScopes);
        Assert.Empty(context.StateUpdates);
    }

    [Fact]
    public async Task QueueClearScopeAsync_NamedScope_OnlyClearsThatScope()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());
        await context.QueueStateUpdateAsync("keyA", "valueA", scopeName: "scopeA");
        await context.QueueStateUpdateAsync("keyB", "valueB", scopeName: "scopeB");

        // Act
        await context.QueueClearScopeAsync("scopeA");

        // Assert
        Assert.DoesNotContain("scopeA:keyA", context.StateUpdates.Keys);
        Assert.Contains("scopeB:keyB", context.StateUpdates.Keys);
    }

    #endregion

    #region ReadStateKeysAsync

    [Fact]
    public async Task ReadStateKeysAsync_ReturnsKeysFromInitialState()
    {
        // Arrange
        Dictionary<string, string> state = new()
        {
            ["__default__:alpha"] = "\"a\"",
            ["__default__:beta"] = "\"b\""
        };
        DurableActivityContext context = new(state, CreateTestExecutor());

        // Act
        HashSet<string> keys = await context.ReadStateKeysAsync();

        // Assert
        Assert.Equal(2, keys.Count);
        Assert.Contains("alpha", keys);
        Assert.Contains("beta", keys);
    }

    [Fact]
    public async Task ReadStateKeysAsync_MergesLocalUpdatesAndDeletions()
    {
        // Arrange
        Dictionary<string, string> state = new()
        {
            ["__default__:existing"] = "\"val\"",
            ["__default__:toDelete"] = "\"val\""
        };
        DurableActivityContext context = new(state, CreateTestExecutor());
        await context.QueueStateUpdateAsync("newKey", "value");
        await context.QueueStateUpdateAsync<string>("toDelete", null);

        // Act
        HashSet<string> keys = await context.ReadStateKeysAsync();

        // Assert
        Assert.Contains("existing", keys);
        Assert.Contains("newKey", keys);
        Assert.DoesNotContain("toDelete", keys);
    }

    [Fact]
    public async Task ReadStateKeysAsync_AfterClearScope_ExcludesInitialState()
    {
        // Arrange
        Dictionary<string, string> state = new() { ["__default__:old"] = "\"val\"" };
        DurableActivityContext context = new(state, CreateTestExecutor());
        await context.QueueClearScopeAsync();
        await context.QueueStateUpdateAsync("new", "value");

        // Act
        HashSet<string> keys = await context.ReadStateKeysAsync();

        // Assert
        Assert.DoesNotContain("old", keys);
        Assert.Contains("new", keys);
    }

    [Fact]
    public async Task ReadStateKeysAsync_WithNamedScope_OnlyReturnsKeysFromThatScope()
    {
        // Arrange
        Dictionary<string, string> state = new()
        {
            ["scopeA:key1"] = "\"val\"",
            ["scopeB:key2"] = "\"val\""
        };
        DurableActivityContext context = new(state, CreateTestExecutor());

        // Act
        HashSet<string> keysA = await context.ReadStateKeysAsync("scopeA");

        // Assert
        Assert.Single(keysA);
        Assert.Contains("key1", keysA);
    }

    #endregion

    #region AddEventAsync

    [Fact]
    public async Task AddEventAsync_AddsEventToCollection()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());
        WorkflowEvent evt = new ExecutorInvokedEvent("test", "test-data");

        // Act
        await context.AddEventAsync(evt);

        // Assert
        Assert.Single(context.Events);
        Assert.Same(evt, context.Events[0]);
    }

    [Fact]
    public async Task AddEventAsync_NullEvent_DoesNotAdd()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act
#pragma warning disable CS8625 // Cannot convert null literal to non-nullable reference type.
        await context.AddEventAsync(null);
#pragma warning restore CS8625

        // Assert
        Assert.Empty(context.Events);
    }

    #endregion

    #region SendMessageAsync

    [Fact]
    public async Task SendMessageAsync_SerializesMessageWithTypeName()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act
        await context.SendMessageAsync("hello");

        // Assert
        Assert.Single(context.SentMessages);
        Assert.Equal(typeof(string).AssemblyQualifiedName, context.SentMessages[0].TypeName);
        Assert.NotNull(context.SentMessages[0].Data);
    }

    [Fact]
    public async Task SendMessageAsync_NullMessage_DoesNotAdd()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act
#pragma warning disable CS8625 // Cannot convert null literal to non-nullable reference type.
        await context.SendMessageAsync(null);
#pragma warning restore CS8625

        // Assert
        Assert.Empty(context.SentMessages);
    }

    #endregion

    #region YieldOutputAsync

    [Fact]
    public async Task YieldOutputAsync_AddsWorkflowOutputEvent()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act
        await context.YieldOutputAsync("result");

        // Assert
        Assert.Single(context.Events);
        WorkflowOutputEvent outputEvent = Assert.IsType<WorkflowOutputEvent>(context.Events[0]);
        Assert.Equal("result", outputEvent.Data);
    }

    [Fact]
    public async Task YieldOutputAsync_NullOutput_DoesNotAdd()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act
#pragma warning disable CS8625 // Cannot convert null literal to non-nullable reference type.
        await context.YieldOutputAsync(null);
#pragma warning restore CS8625

        // Assert
        Assert.Empty(context.Events);
    }

    #endregion

    #region RequestHaltAsync

    [Fact]
    public async Task RequestHaltAsync_SetsHaltRequestedAndAddsEvent()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Act
        await context.RequestHaltAsync();

        // Assert
        Assert.True(context.HaltRequested);
        Assert.Single(context.Events);
        Assert.IsType<DurableHaltRequestedEvent>(context.Events[0]);
    }

    #endregion

    #region Properties

    [Fact]
    public void TraceContext_ReturnsNull()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Assert
        Assert.Null(context.TraceContext);
    }

    [Fact]
    public void ConcurrentRunsEnabled_ReturnsFalse()
    {
        // Arrange
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Assert
        Assert.False(context.ConcurrentRunsEnabled);
    }

    [Fact]
    public async Task Constructor_NullInitialState_CreatesEmptyState()
    {
        // Arrange & Act
        DurableActivityContext context = new(null, CreateTestExecutor());

        // Assert
        string? result = await context.ReadStateAsync<string>("anything");
        Assert.Null(result);
    }

    #endregion
}
