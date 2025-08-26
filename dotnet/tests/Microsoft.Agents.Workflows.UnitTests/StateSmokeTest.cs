// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.UnitTests;

public class StateSmokeTest
{
    [Fact]
    public void Test_ScopeId_Equality()
    {
        // The rules of ScopeId are simple: Private executor scopes (executorId, scopeId=null) are only equal to
        // themselves. Public ScopeIds are equal when their scopeNames are equal, regardless of executorId.

        ScopeId privateScope1 = new("executor1", null);
        ScopeId privateScope2 = new("executor2", null);

        Assert.NotEqual(privateScope1, privateScope2);
        Assert.Equal(privateScope1, new ScopeId("executor1", null));

        ScopeId sharedScope1 = new("executor1", "sharedScope");
        ScopeId sharedScope2 = new("executor2", "sharedScope");

        Assert.Equal(sharedScope1, sharedScope2);
        Assert.NotEqual(sharedScope1, new ScopeId("executor1", "differentScope"));
        Assert.NotEqual(sharedScope1, privateScope1);
    }

    [Fact]
    public void Test_UpdateKey_Equality()
    {
        // The rules of UpdateKey are different from ScopeId. In the case of "shared scope",
        // two update keys with different ExecutorIds are not the same.

        const string Key1 = "key1";
        const string Key2 = "key2";
        UpdateKey privateScope1Key = new("executor1", null, Key1);
        UpdateKey privateScope1Key2 = new("executor1", null, Key2);

        Assert.NotEqual(privateScope1Key, privateScope1Key2);

        UpdateKey privateScope2Key = new("executor2", null, Key1);

        Assert.NotEqual(privateScope1Key, privateScope2Key);

        UpdateKey scope1Executor1Key = new("executor1", "sharedScope", Key1);
        UpdateKey scope1Executor2Key = new("executor2", "sharedScope", Key1);

        Assert.NotEqual(scope1Executor1Key, scope1Executor2Key);
    }

    [Fact]
    public async Task Test_ReadQueueUpdateAsync()
    {
        ScopeId sharedScope1 = new("executor1", "sharedScope");
        ScopeId sharedScope2 = new("executor2", "sharedScope");

        StateManager manager = new();

        // Default reads on "object" should be null
        const string Key = "key1";
        Assert.Null(await manager.ReadStateAsync<object>(sharedScope1, Key));
        Assert.Null(await manager.ReadStateAsync<object>(sharedScope1, Key));

        await manager.WriteStateAsync(sharedScope1, Key, new object());

        // After writing, we should be able to read the value from the executor's scope
        // but not the shared scope yet
        Assert.NotNull(await manager.ReadStateAsync<object>(sharedScope1, Key));
        Assert.Null(await manager.ReadStateAsync<object>(sharedScope2, Key));

        // Writes to one key should not impact other keys
        Assert.Null(await manager.ReadStateAsync<object>(sharedScope1, "key2"));

        // Publish the write
        await manager.PublishUpdatesAsync(tracer: null);

        // Now all the executors should be able to see the new state
        Assert.NotNull(await manager.ReadStateAsync<object>(sharedScope1, Key));
        Assert.NotNull(await manager.ReadStateAsync<object>(sharedScope2, Key));
    }

    [Fact]
    public async Task Test_ConflictingWritesRaiseExceptionAsync()
    {
        ScopeId sharedScope1 = new("executor1", "sharedScope");
        ScopeId sharedScope2 = new("executor2", "sharedScope");

        StateManager manager = new();

        const string Key = "key1";
        const string Value1 = "1";
        const string Value2 = "2";

        // Write values from both executors
        await manager.WriteStateAsync(sharedScope1, Key, Value1);
        await manager.WriteStateAsync(sharedScope2, Key, Value2);

        // Check that reading each will result in the right value
        Assert.Equal(Value1, await manager.ReadStateAsync<string>(sharedScope1, Key));
        Assert.Equal(Value2, await manager.ReadStateAsync<string>(sharedScope2, Key));

        // Try to publish the updates
        try
        {
            await manager.PublishUpdatesAsync(tracer: null);
            Assert.Fail("Expected InvalidOperationException due to conflicting writes.");
        }
        catch (InvalidOperationException)
        {
        }
        catch (Exception ex)
        {
            Assert.Fail($"Expected InvalidOperationException, but got {ex.GetType().Name}.");
        }
    }
}
