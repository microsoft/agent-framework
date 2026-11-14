// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class StateManagerTests
{
    [Fact]
    public async Task Test_SharedScope_ReadKeysAsync()
    {
        const string? ScopeName = "sharedScope";
        await RunScopeKeysTestAsync(ScopeName, isSharedScope: true);
    }

    [Fact]
    public async Task Test_PrivateScope_ReadKeysAsync()
    {
        const string? ScopeName = null;
        await RunScopeKeysTestAsync(ScopeName, isSharedScope: false);
    }

    private static async Task RunScopeKeysTestAsync(string? scopeName, bool isSharedScope)
    {
        const string SelfExecutorId = "executor1";
        const string OtherExecutorId = "executor2";
        const string Key1 = "key1";
        HashSet<string> ExpectedAfterWrite = [Key1];

        StateManager manager = new();
        ScopeId sharedScopeSelfView = new(SelfExecutorId, scopeName);
        ScopeId sharedScopeOtherView = new(OtherExecutorId, scopeName);

        // Assert baseline: neither executor sees any keys
        HashSet<string> selfKeys = await manager.ReadKeysAsync(sharedScopeSelfView);
        Assert.Empty(selfKeys ?? []);

        HashSet<string> otherKeys = await manager.ReadKeysAsync(sharedScopeOtherView);
        Assert.Empty(otherKeys ?? []);

        // Act 1: Write a key from the self executor's view of the shared scope

        await manager.WriteStateAsync(sharedScopeSelfView, Key1, "value1");

        // Assert 1: The self executor should see the key immediately, but the other executor should not
        selfKeys = await manager.ReadKeysAsync(sharedScopeSelfView);
        Assert.True(selfKeys.SetEquals(ExpectedAfterWrite));

        otherKeys = await manager.ReadKeysAsync(sharedScopeOtherView);
        Assert.Empty(otherKeys ?? []);

        // Act 2: Publish the updates
        await manager.PublishUpdatesAsync(tracer: null);

        // Assert 2: Both executors should see the key now, if sharedScope
        selfKeys = await manager.ReadKeysAsync(sharedScopeSelfView);
        Assert.True(selfKeys.SetEquals(ExpectedAfterWrite));

        otherKeys = await manager.ReadKeysAsync(sharedScopeOtherView);

        if (isSharedScope)
        {
            Assert.True(otherKeys.SetEquals(ExpectedAfterWrite));
        }
        else
        {
            Assert.Empty(otherKeys ?? []);
        }

        // Act 3: Clear the state from the self executor's view of the shared scope
        await manager.WriteStateAsync<string?>(sharedScopeSelfView, Key1, null);

        // Assert 3: The self executor should not see the key immediately, but the other executor should still see it if sharedScope
        selfKeys = await manager.ReadKeysAsync(sharedScopeSelfView);
        Assert.Empty(selfKeys ?? []);

        otherKeys = await manager.ReadKeysAsync(sharedScopeOtherView);
        if (isSharedScope)
        {
            Assert.True(otherKeys.SetEquals(ExpectedAfterWrite));
        }
        else
        {
            Assert.Empty(otherKeys ?? []);
        }

        // Act 4: Publish the updates
        await manager.PublishUpdatesAsync(tracer: null);

        // Assert 4: Neither executor should see the key now
        selfKeys = await manager.ReadKeysAsync(sharedScopeSelfView);
        Assert.Empty(selfKeys ?? []);

        otherKeys = await manager.ReadKeysAsync(sharedScopeOtherView);
        Assert.Empty(otherKeys ?? []);
    }

    [Fact]
    public async Task Test_SharedScope_ValueLifecycleAsync()
    {
        const string? ScopeName = "sharedScope";
        await RunValueLifecycleTestAsync(ScopeName, isSharedScope: true);
    }

    [Fact]
    public async Task Test_PrivateScope_ValueLifecycleAsync()
    {
        const string? ScopeName = null;
        await RunValueLifecycleTestAsync(ScopeName, isSharedScope: false);
    }

    private static async Task RunValueLifecycleTestAsync(string? scopeName, bool isSharedScope)
    {
        const string SelfExecutorId = "executor1";
        const string OtherExecutorId = "executor2";
        const string Key1 = "key1", Key2 = "key2";
        const string Value1 = "value1", Value2 = "value2";

        StateManager manager = new();
        ScopeId scopeSelfView = new(SelfExecutorId, scopeName);
        ScopeId scopeOtherView = new(OtherExecutorId, scopeName);

        Assert.Equal(scopeSelfView == scopeOtherView, isSharedScope);

        // Assert baseline: neither executor sees any keys or values
        string? selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        string? selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        Assert.Null(selfValue1);
        Assert.Null(selfValue2);

        string? otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        string? otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        Assert.Null(otherValue1);
        Assert.Null(otherValue2);

        // Act 1: Write a value from the self executor's view of the shared scope
        await manager.WriteStateAsync(scopeSelfView, Key1, Value1);

        // Assert 1: The self executor should see the value immediately, but the other executor should not
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        Assert.Equal(Value1, selfValue1);

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        Assert.Null(selfValue2);

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        Assert.Null(otherValue1);

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        Assert.Null(otherValue2);

        // Act 2: Write a value from the other executor's view of the shared scope
        await manager.WriteStateAsync(scopeOtherView, Key2, Value2);

        // Assert 2: The other executor should see the value immediately, but the self executor should not
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        Assert.Equal(Value1, selfValue1);

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        Assert.Null(selfValue2);

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        Assert.Null(otherValue1);

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        Assert.Equal(Value2, otherValue2);

        // Act 3: Publish the updates
        await manager.PublishUpdatesAsync(tracer: null);

        // Assert 3: Both executors should see both values now, if the scope is shared
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        Assert.Equal(Value1, selfValue1);

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        if (isSharedScope)
        {
            Assert.Equal(Value2, selfValue2);
        }
        else
        {
            Assert.Null(selfValue2);
        }

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        if (isSharedScope)
        {
            Assert.Equal(Value1, otherValue1);
        }
        else
        {
            Assert.Null(otherValue1);
        }

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        Assert.Equal(Value2, otherValue2);

        // Act 4: Clear the value from the self executor's view of the shared scope
        await manager.ClearStateAsync(scopeSelfView);

        // Assert 4: The self executor should not see either value immediately, but the other executor should still see both
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        Assert.Null(selfValue1);

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        Assert.Null(selfValue2);

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        if (isSharedScope)
        {
            Assert.Equal(Value1, otherValue1);
        }
        else
        {
            Assert.Null(otherValue1);
        }

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        Assert.Equal(Value2, otherValue2);

        // Act 5: Publish the updates
        await manager.PublishUpdatesAsync(tracer: null);

        // Assert 5: Neither executor should see either value now
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        Assert.Null(selfValue1);

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        Assert.Null(selfValue2);

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        Assert.Null(otherValue1);

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        if (isSharedScope)
        {
            Assert.Null(otherValue2);
        }
        else
        {
            Assert.Equal(Value2, otherValue2);
        }

        // Restore the written state of both keys
        await manager.WriteStateAsync(scopeSelfView, Key1, Value1);
        await manager.WriteStateAsync(scopeOtherView, Key2, Value2);
        await manager.PublishUpdatesAsync(tracer: null);

        // Act 6: Delete Key1 from the other executor's view of the shared scope
        await manager.WriteStateAsync<string?>(scopeOtherView, Key1, null);

        // Assert 6: The other executor should not see Key1 immediately, but should still see Key2. The self executor should still see both.
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        Assert.Equal(Value1, selfValue1);

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        if (isSharedScope)
        {
            Assert.Equal(Value2, selfValue2);
        }
        else
        {
            Assert.Null(selfValue2);
        }

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        Assert.Null(otherValue1);

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        Assert.Equal(Value2, otherValue2);

        // Act 7: Delete Key2 from the self executor's view of the shared scope
        await manager.WriteStateAsync<string?>(scopeSelfView, Key2, null);

        // Assert 7: The self executor should not see Key2 immediately, but should still see Key1.
        // The other executor should not see Key1, but should still see Key2.
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        Assert.Equal(Value1, selfValue1);

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        Assert.Null(selfValue2);

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        Assert.Null(otherValue1);

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        Assert.Equal(Value2, otherValue2);

        // Act 8: Publish the updates
        await manager.PublishUpdatesAsync(tracer: null);

        // Assert 8: Neither executor should see either value now
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        if (isSharedScope)
        {
            Assert.Null(selfValue1);
        }
        else
        {
            Assert.Equal(Value1, selfValue1);
        }

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        Assert.Null(selfValue2);

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        Assert.Null(otherValue1);

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        if (isSharedScope)
        {
            Assert.Null(otherValue2);
        }
        else
        {
            Assert.Equal(Value2, otherValue2);
        }
    }

    [Fact]
    public async Task Test_SharedScope_ConflictingUpdatesAsync()
    {
        const string? ScopeName = "sharedScope";
        await RunConflictingUpdatesTest_WriteVsWriteAsync(ScopeName, isSharedScope: true);
        await RunConflictingUpdatesTest_WriteVsDeleteAsync(ScopeName, isSharedScope: true);
        await RunConflictingUpdatesTest_WriteVsClearAsync(ScopeName, isSharedScope: true);
    }

    [Fact]
    public async Task Test_PrivateScope_ConflictingUpdatesAsync()
    {
        const string? ScopeName = null;
        await RunConflictingUpdatesTest_WriteVsWriteAsync(ScopeName, isSharedScope: false);
        await RunConflictingUpdatesTest_WriteVsDeleteAsync(ScopeName, isSharedScope: false);
        await RunConflictingUpdatesTest_WriteVsClearAsync(ScopeName, isSharedScope: false);
    }

    [Fact]
    public async Task Test_FailedPublish_LeavesUpdatesQueuedAsync()
    {
        // A conflicting write to a shared scope makes PublishUpdatesAsync throw. The queued updates
        // must survive that: the next publish sees the same conflict rather than silently finding an
        // empty queue, and nothing half-published is dropped.
        StateManager manager = new();
        ScopeId selfView = new("executor1", "shared");
        ScopeId otherView = new("executor2", "shared");

        await manager.WriteStateAsync(selfView, "key1", "value1");
        await manager.WriteStateAsync(otherView, "key1", "value2");

        await Assert.ThrowsAsync<InvalidOperationException>(async () => await manager.PublishUpdatesAsync(tracer: null));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await manager.PublishUpdatesAsync(tracer: null));
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await manager.ExportStateAsync());
    }

    [Fact]
    public async Task Test_SuccessfulPublish_EmptiesTheQueueAsync()
    {
        StateManager manager = new();
        ScopeId scope = new("executor1", "shared");

        await manager.WriteStateAsync(scope, "key1", "value1");
        await manager.PublishUpdatesAsync(tracer: null);

        Dictionary<ScopeKey, PortableValue> exported = await manager.ExportStateAsync();
        Assert.Single(exported);
        Assert.Equal("value1", await manager.ReadStateAsync<string>(scope, "key1"));
    }

    private static async Task RunConflictingUpdatesTest_WriteVsWriteAsync(string? scopeName, bool isSharedScope)
    {
        const string SelfExecutorId = "executor1";
        const string OtherExecutorId = "executor2";
        const string Key1 = "key1";
        const string Value1 = "value", Value2 = "value";

        // Arrange
        StateManager manager = new();
        ScopeId scopeSelfView = new(SelfExecutorId, scopeName);
        ScopeId scopeOtherView = new(OtherExecutorId, scopeName);
        Assert.Equal(scopeSelfView == scopeOtherView, isSharedScope);

        // Act 1: Write a conflicting value from the self executor's view of the shared scope
        // Note that conflicting means update to the same key, not that the values are necessarily different.
        // We do not have any logic to resolve equivalent updates from different executors as idempotent.
        await manager.WriteStateAsync(scopeSelfView, Key1, Value1);
        await manager.WriteStateAsync(scopeOtherView, Key1, Value2);

        async Task actAsync() => await manager.PublishUpdatesAsync(tracer: null);

        if (isSharedScope)
        {
            await Assert.ThrowsAsync<InvalidOperationException>(actAsync);
        }
        else
        {
            Assert.Null(await Record.ExceptionAsync(actAsync));
        }
    }

    private static async Task RunConflictingUpdatesTest_WriteVsDeleteAsync(string? scopeName, bool isSharedScope)
    {
        const string SelfExecutorId = "executor1";
        const string OtherExecutorId = "executor2";
        const string Key1 = "key1", Key2 = "key2";
        const string Value1 = "value", Value2 = "value";

        // Arrange
        StateManager manager = new();
        ScopeId scopeSelfView = new(SelfExecutorId, scopeName);
        ScopeId scopeOtherView = new(OtherExecutorId, scopeName);
        Assert.Equal(scopeSelfView == scopeOtherView, isSharedScope);

        await manager.WriteStateAsync(scopeSelfView, Key1, Value1);
        await manager.WriteStateAsync(scopeOtherView, Key2, Value2);
        await manager.PublishUpdatesAsync(tracer: null);

        // Act: Update the key from one executor and delete it from another
        await manager.WriteStateAsync(scopeSelfView, Key1, "newValue");
        await manager.ClearStateAsync(scopeOtherView, Key1);
        async Task actAsync() => await manager.PublishUpdatesAsync(tracer: null);

        if (isSharedScope)
        {
            await Assert.ThrowsAsync<InvalidOperationException>(actAsync);
        }
        else
        {
            Assert.Null(await Record.ExceptionAsync(actAsync));
        }
    }

    private static async Task RunConflictingUpdatesTest_WriteVsClearAsync(string? scopeName, bool isSharedScope)
    {
        const string SelfExecutorId = "executor1";
        const string OtherExecutorId = "executor2";
        const string Key1 = "key1", Key2 = "key2";
        const string Value1 = "value", Value2 = "value";

        // Arrange
        StateManager manager = new();
        ScopeId scopeSelfView = new(SelfExecutorId, scopeName);
        ScopeId scopeOtherView = new(OtherExecutorId, scopeName);
        Assert.Equal(scopeSelfView == scopeOtherView, isSharedScope);

        await manager.WriteStateAsync(scopeSelfView, Key1, Value1);
        await manager.WriteStateAsync(scopeOtherView, Key2, Value2);
        await manager.PublishUpdatesAsync(tracer: null);

        // Act: Update the key from one, and clear the entire scope from another
        await manager.WriteStateAsync(scopeSelfView, Key1, "newValue");
        await manager.ClearStateAsync(scopeOtherView);
        async Task actAsync() => await manager.PublishUpdatesAsync(tracer: null);

        // Assert
        if (isSharedScope)
        {
            await Assert.ThrowsAsync<InvalidOperationException>(actAsync);
        }
        else
        {
            Assert.Null(await Record.ExceptionAsync(actAsync));
        }
    }

    private static void VerifyIs<TExpectedType>(PortableValue? candidatePV, TExpectedType value)
    {
        Assert.NotNull(candidatePV);
        Assert.True(candidatePV.Is(out TExpectedType? candidateValue));
        Assert.Equal(value, candidateValue);
    }

    private static void VerifyIsNot<TExpectedType>(PortableValue? candidatePV)
    {
        Assert.NotNull(candidatePV);
        Assert.False(candidatePV.Is(out TExpectedType? _));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Test_LoadPortableValueStateAsync(bool publishStateUpdates)
    {
        ScopeId scope = new("executor1");
        const string StringValue = "string";
        const int IntValue = 42;
        ScopeKey ScopeKey = new("executor1", "scope", "key");
        PortableValue PortableValueValue = new(StringValue);

        // Arrange
        StateManager manager = new();
        await manager.WriteStateAsync(scope, nameof(StringValue), StringValue);
        await manager.WriteStateAsync(scope, nameof(IntValue), IntValue);
        await manager.WriteStateAsync(scope, nameof(ScopeKey), ScopeKey);
        await manager.WriteStateAsync(scope, nameof(PortableValueValue), PortableValueValue);

        if (publishStateUpdates)
        {
            await manager.PublishUpdatesAsync(tracer: null);
        }

        // Act & Assert - Read as the original types
        PortableValue? stringAsPV = await manager.ReadStateAsync<PortableValue>(scope, nameof(StringValue));
        VerifyIs(stringAsPV, StringValue);
        VerifyIsNot<int>(stringAsPV);
        VerifyIsNot<ChatMessage>(stringAsPV);
        VerifyIsNot<PortableValue>(stringAsPV);

        PortableValue? intAsPV = await manager.ReadStateAsync<PortableValue>(scope, nameof(IntValue));
        VerifyIsNot<string>(intAsPV);
        VerifyIs(intAsPV, IntValue);
        VerifyIsNot<ChatMessage>(intAsPV);
        VerifyIsNot<PortableValue>(intAsPV);

        PortableValue? scopeKeyAsPV = await manager.ReadStateAsync<PortableValue>(scope, nameof(ScopeKey));
        VerifyIsNot<string>(scopeKeyAsPV);
        VerifyIsNot<int>(scopeKeyAsPV);
        VerifyIs(scopeKeyAsPV, ScopeKey);
        VerifyIsNot<PortableValue>(scopeKeyAsPV);

        PortableValue? pvAsPV = await manager.ReadStateAsync<PortableValue>(scope, nameof(PortableValueValue));
        VerifyIs(pvAsPV, StringValue);
        VerifyIsNot<int>(pvAsPV);
        VerifyIsNot<ChatMessage>(pvAsPV);

        // Check that we don't double-wrap stored PortableValues on the out path
        VerifyIsNot<PortableValue>(pvAsPV);
    }

    [Fact]
    public async Task Test_LoadPortableValueState_AfterSerializationAsync()
    {
        ScopeId scope = new("executor1");
        const string StringValue = "string";
        const int IntValue = 42;
        ScopeKey ScopeKey = new("executor1", "scope", "key");
        PortableValue PortableValueValue = new(StringValue);

        // Arrange
        StateManager manager = new();
        await manager.WriteStateAsync(scope, nameof(StringValue), StringValue);
        await manager.WriteStateAsync(scope, nameof(IntValue), IntValue);
        await manager.WriteStateAsync(scope, nameof(ScopeKey), ScopeKey);
        await manager.WriteStateAsync(scope, nameof(PortableValueValue), PortableValueValue);

        await manager.PublishUpdatesAsync(tracer: null);

        Dictionary<ScopeKey, PortableValue> exportedState = await manager.ExportStateAsync();
        Dictionary<ScopeKey, PortableValue> serializedState = JsonSerializationTests.RunJsonRoundtrip(exportedState);
        Checkpoint testCheckpoint = new(0, JsonSerializationTests.CreateTestWorkflowInfo(), new([], [], []), serializedState, []);

        manager = new();
        await manager.ImportStateAsync(testCheckpoint);

        // Act & Assert - Read as the original types
        PortableValue? stringAsPV = await manager.ReadStateAsync<PortableValue>(scope, nameof(StringValue));
        VerifyIs(stringAsPV, StringValue);
        VerifyIsNot<int>(stringAsPV);
        VerifyIsNot<ChatMessage>(stringAsPV);

        PortableValue? intAsPV = await manager.ReadStateAsync<PortableValue>(scope, nameof(IntValue));
        VerifyIsNot<string>(intAsPV);
        VerifyIs(intAsPV, IntValue);
        VerifyIsNot<ChatMessage>(intAsPV);

        PortableValue? scopeKeyAsPV = await manager.ReadStateAsync<PortableValue>(scope, nameof(ScopeKey));
        VerifyIsNot<string>(scopeKeyAsPV);
        VerifyIsNot<int>(scopeKeyAsPV);
        VerifyIs(scopeKeyAsPV, ScopeKey);
        VerifyIsNot<PortableValue>(scopeKeyAsPV);

        PortableValue? pvAsPV = await manager.ReadStateAsync<PortableValue>(scope, nameof(PortableValueValue));
        VerifyIs(pvAsPV, StringValue);
        VerifyIsNot<int>(pvAsPV);
        VerifyIsNot<ChatMessage>(pvAsPV);

        // Check that we don't double-wrap stored PortableValues on the out path
        VerifyIsNot<PortableValue>(pvAsPV);
    }

    [Theory]
    [InlineData("step_results")]
    [InlineData(null)]
    public async Task Test_ConcurrentExecutors_QueueAndReadState_WithoutCorruptionAsync(string? scopeName)
    {
        // InProcessRunner.RunSuperstepAsync delivers a superstep's messages to every receiving executor
        // concurrently (one task per receiver, awaited together), and each executor reaches the same
        // StateManager through its bound IWorkflowContext. Before the manager synchronized access to its
        // queued-update dictionary, executors that finished in the same superstep raced on it and the
        // run failed with "Operations that change non-concurrent collections must have exclusive access"
        // — observed in a production host when four executors completed within 14 ms of each other.
        const int Executors = 64;
        const int WritesPerExecutor = 200;

        StateManager manager = new();

        await Task.WhenAll(Enumerable.Range(0, Executors).Select(e => Task.Run(async () =>
        {
            ScopeId scope = new($"executor{e}", scopeName);
            for (int i = 0; i < WritesPerExecutor; i++)
            {
                string key = $"e{e}_key{i}";
                await manager.WriteStateAsync(scope, key, $"value{e}:{i}");
                Assert.Equal($"value{e}:{i}", await manager.ReadStateAsync<string>(scope, key));
                _ = await manager.ReadKeysAsync(scope);
            }
        })));

        await manager.PublishUpdatesAsync(tracer: null);

        bool isSharedScope = scopeName is not null;
        for (int e = 0; e < Executors; e++)
        {
            ScopeId scope = new($"executor{e}", scopeName);
            HashSet<string> keys = await manager.ReadKeysAsync(scope);

            // A shared scope is one bag every executor writes into; a private scope holds only its owner's keys.
            Assert.Equal(isSharedScope ? Executors * WritesPerExecutor : WritesPerExecutor, keys.Count);
            Assert.Equal($"value{e}:{WritesPerExecutor - 1}", await manager.ReadStateAsync<string>(scope, $"e{e}_key{WritesPerExecutor - 1}"));
        }

        // Nothing may be left queued after a publish, whichever thread queued it.
        Dictionary<ScopeKey, PortableValue> exported = await manager.ExportStateAsync();
        Assert.Equal(Executors * WritesPerExecutor, exported.Count);
    }
}
