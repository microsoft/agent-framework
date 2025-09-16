// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.UnitTests;

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
        selfKeys.Should().BeEmpty("there should be no keys in an empty StateManager");

        HashSet<string> otherKeys = await manager.ReadKeysAsync(sharedScopeOtherView);
        otherKeys.Should().BeEmpty("there should be no keys in an empty StateManager");

        // Act 1: Write a key from the self executor's view of the shared scope

        await manager.WriteStateAsync(sharedScopeSelfView, Key1, "value1");

        // Assert 1: The self executor should see the key immediately, but the other executor should not
        selfKeys = await manager.ReadKeysAsync(sharedScopeSelfView);
        selfKeys.SetEquals(ExpectedAfterWrite).Should().BeTrue("writes should be visible immediately to the writing executor");

        otherKeys = await manager.ReadKeysAsync(sharedScopeOtherView);
        otherKeys.Should().BeEmpty(isSharedScope ? "writes should not be visible to other executors until published"
                                                 : "writes to private scopes should not be visible across executors");

        // Act 2: Publish the updates
        await manager.PublishUpdatesAsync(tracer: null);

        // Assert 2: Both executors should see the key now, if sharedScope
        selfKeys = await manager.ReadKeysAsync(sharedScopeSelfView);
        selfKeys.SetEquals(ExpectedAfterWrite).Should().BeTrue("published writes should be visible to all executors");

        otherKeys = await manager.ReadKeysAsync(sharedScopeOtherView);

        if (isSharedScope)
        {
            otherKeys.SetEquals(ExpectedAfterWrite).Should().BeTrue("published writes should be visible to all executors");
        }
        else
        {
            otherKeys.Should().BeEmpty("writes to private scopes should not be visible across executors");
        }

        // Act 3: Clear the state from the self executor's view of the shared scope
        await manager.WriteStateAsync<string?>(sharedScopeSelfView, Key1, null);

        // Assert 3: The self executor should not see the key immediately, but the other executor should still see it if sharedScope
        selfKeys = await manager.ReadKeysAsync(sharedScopeSelfView);
        selfKeys.Should().BeEmpty("deletes should be visible immediately to the writing executor");

        otherKeys = await manager.ReadKeysAsync(sharedScopeOtherView);
        if (isSharedScope)
        {
            otherKeys.SetEquals(ExpectedAfterWrite).Should().BeTrue("published writes should be visible to all executors");
        }
        else
        {
            otherKeys.Should().BeEmpty("writes to private scopes should not be visible across executors");
        }

        // Act 4: Publish the updates
        await manager.PublishUpdatesAsync(tracer: null);

        // Assert 4: Neither executor should see the key now
        selfKeys = await manager.ReadKeysAsync(sharedScopeSelfView);
        selfKeys.Should().BeEmpty("published deletes should be visible to all executors");

        otherKeys = await manager.ReadKeysAsync(sharedScopeOtherView);
        otherKeys.Should().BeEmpty(isSharedScope ? "published deletes should be visible to all executors"
                                                 : "writes to private scopes should not be visible across executors");
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

        isSharedScope.Should().Be(scopeSelfView == scopeOtherView);

        // Assert baseline: neither executor sees any keys or values
        string? selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        string? selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        selfValue1.Should().BeNull("there should be no values in an empty StateManager");
        selfValue2.Should().BeNull("there should be no values in an empty StateManager");

        string? otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        string? otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        otherValue1.Should().BeNull("there should be no values in an empty StateManager");
        otherValue2.Should().BeNull("there should be no values in an empty StateManager");

        // Act 1: Write a value from the self executor's view of the shared scope
        await manager.WriteStateAsync(scopeSelfView, Key1, Value1);

        // Assert 1: The self executor should see the value immediately, but the other executor should not
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        selfValue1.Should().Be(Value1, "writes should be visible immediately to the writing executor");

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        selfValue2.Should().BeNull("uninvolved keys' state/value should not change after a write");

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        otherValue1.Should().BeNull(isSharedScope ? "writes should not be visible to other executors until published (key1: written by self, read by other)"
                                                  : "writes to private scopes should not be visible across executors");

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        otherValue2.Should().BeNull("uninvolved keys' state/value should not change after a write");

        // Act 2: Write a value from the other executor's view of the shared scope
        await manager.WriteStateAsync(scopeOtherView, Key2, Value2);

        // Assert 2: The other executor should see the value immediately, but the self executor should not
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        selfValue1.Should().Be(Value1, "uninvolved keys' state/value should not change after a write");

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        selfValue2.Should().BeNull(isSharedScope ? "writes should not be visible to other executors until published (key2: written by other, read by self)"
                                                 : "writes to private scopes should not be visible across executors");

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        otherValue1.Should().BeNull(isSharedScope ? "writes should not be visible to other executors until published (key1: written by self, read by other)"
                                                  : "writes to private scopes should not be visible across executors");

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        otherValue2.Should().Be(Value2, "writes should be visible immediately to the writing executor");

        // Act 3: Publish the updates
        await manager.PublishUpdatesAsync(tracer: null);

        // Assert 3: Both executors should see both values now, if the scope is shared
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        selfValue1.Should().Be(Value1, "published writes should be visible to all executors (key1: written by self, read by self)");

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        if (isSharedScope)
        {
            selfValue2.Should().Be(Value2, "published writes should be visible to all executors (key2: written by other, read by self)");
        }
        else
        {
            selfValue2.Should().BeNull("writes to private scopes should not be visible across executors");
        }

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        if (isSharedScope)
        {
            otherValue1.Should().Be(Value1, "published writes should be visible to all executors (key1: written by self, read by other)");
        }
        else
        {
            otherValue1.Should().BeNull("writes to private scopes should not be visible across executors");
        }

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        otherValue2.Should().Be(Value2, "published writes should be visible to all executors (key2: written by other, read by other)");

        // Act 4: Clear the value from the self executor's view of the shared scope
        await manager.ClearStateAsync(scopeSelfView);

        // Assert 4: The self executor should not see either value immediately, but the other executor should still see both
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        selfValue1.Should().BeNull("clears should be visible immediately to the writing executor");

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        selfValue2.Should().BeNull(isSharedScope ? "clears should be visible immediately to the writing executor"
                                                 : "writes to private scopes should not be visible across executors");

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        if (isSharedScope)
        {
            otherValue1.Should().Be(Value1, "clears should not be visible to other executors until published (key2: written by self, read by other)");
        }
        else
        {
            otherValue1.Should().BeNull("writes to private scopes should not be visible across executors");
        }

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        otherValue2.Should().Be(Value2, isSharedScope ? "clears should not be visible to other executors until published (key2: written by self, read by other)"
                                                      : "writes to private scopes should not be visible across executors");

        // Act 5: Publish the updates
        await manager.PublishUpdatesAsync(tracer: null);

        // Assert 5: Neither executor should see either value now
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        selfValue1.Should().BeNull("published clears should be visible to all executors");

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        selfValue2.Should().BeNull(isSharedScope ? "published clears should be visible to all executors"
                                                 : "writes to private scopes should not be visible across executors");

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        otherValue1.Should().BeNull(isSharedScope ? "published clears should be visible to all executors"
                                                  : "writes to private scopes should not be visible across executors");

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        if (isSharedScope)
        {
            otherValue2.Should().BeNull("published clears should be visible to all executors");
        }
        else
        {
            otherValue2.Should().Be(Value2, "writes to private scopes should not be visible across executors");
        }

        // Restore the written state of both keys
        await manager.WriteStateAsync(scopeSelfView, Key1, Value1);
        await manager.WriteStateAsync(scopeOtherView, Key2, Value2);
        await manager.PublishUpdatesAsync(tracer: null);

        // Act 6: Delete Key1 from the other executor's view of the shared scope
        await manager.WriteStateAsync<string?>(scopeOtherView, Key1, null);

        // Assert 6: The other executor should not see Key1 immediately, but should still see Key2. The self executor should still see both.
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        selfValue1.Should().Be(Value1, isSharedScope ? "deletes should not be visible to other executors until published (key1: written by other, read by self)"
                                                     : "writes to private scopes should not be visible across executors");

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        if (isSharedScope)
        {
            selfValue2.Should().Be(Value2, "uninvolved keys' state/value should not change after a delete");
        }
        else
        {
            selfValue2.Should().BeNull("writes to private scopes should not be visible across executors");
        }

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        otherValue1.Should().BeNull(isSharedScope ? "deletes should be visible immediately to the writing executor"
                                                  : "writes to private scopes should not be visible across executors");

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        otherValue2.Should().Be(Value2, "uninvolved keys' state/value should not change after a delete");

        // Act 7: Delete Key2 from the self executor's view of the shared scope
        await manager.WriteStateAsync<string?>(scopeSelfView, Key2, null);

        // Assert 7: The self executor should not see Key2 immediately, but should still see Key1.
        // The other executor should not see Key1, but should still see Key2.
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        selfValue1.Should().Be(Value1, isSharedScope ? "deletes should not be visible to other executors until published (key1: written by other, read by self)"
                                                     : "writes to private scopes should not be visible across executors");

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        selfValue2.Should().BeNull(isSharedScope ? "deletes should be visible immediately to the writing executor"
                                                 : "writes to private scopes should not be visible across executors");

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        otherValue1.Should().BeNull(isSharedScope ? "deletes should be visible immediately to the writing executor"
                                                  : "writes to private scopes should not be visible across executors");

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        otherValue2.Should().Be(Value2, isSharedScope ? "deletes should not be visible to other executors until published (key2: written by self, read by other)"
                                                      : "writes to private scopes should not be visible across executors");

        // Act 8: Publish the updates
        await manager.PublishUpdatesAsync(tracer: null);

        // Assert 8: Neither executor should see either value now
        selfValue1 = await manager.ReadStateAsync<string>(scopeSelfView, Key1);
        if (isSharedScope)
        {
            selfValue1.Should().BeNull("published deletes should be visible to all executors");
        }
        else
        {
            selfValue1.Should().Be(Value1, "writes to private scopes should not be visible across executors");
        }

        selfValue2 = await manager.ReadStateAsync<string>(scopeSelfView, Key2);
        selfValue2.Should().BeNull(isSharedScope ? "published deletes should be visible to all executors"
                                                 : "writes to private scopes should not be visible across executors");

        otherValue1 = await manager.ReadStateAsync<string>(scopeOtherView, Key1);
        otherValue1.Should().BeNull(isSharedScope ? "published deletes should be visible to all executors"
                                                  : "writes to private scopes should not be visible across executors");

        otherValue2 = await manager.ReadStateAsync<string>(scopeOtherView, Key2);
        if (isSharedScope)
        {
            otherValue2.Should().BeNull("published deletes should be visible to all executors");
        }
        else
        {
            otherValue2.Should().Be(Value2, "writes to private scopes should not be visible across executors");
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
        isSharedScope.Should().Be(scopeSelfView == scopeOtherView);

        // Act 1: Write a conflicting value from the self executor's view of the shared scope
        // Note that conflicting means update to the same key, not that the values are necessarily different.
        // We do not have any logic to resolve equivalent updates from different executors as idempotent.
        await manager.WriteStateAsync(scopeSelfView, Key1, Value1);
        await manager.WriteStateAsync(scopeOtherView, Key1, Value2);

        Func<Task> act = async () => await manager.PublishUpdatesAsync(tracer: null);

        if (isSharedScope)
        {
            await act.Should().ThrowAsync<InvalidOperationException>("conflicting writes to the same key should raise an exception when published");
        }
        else
        {
            await act.Should().NotThrowAsync("writes to private scopes should not be visible across executors");
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
        isSharedScope.Should().Be(scopeSelfView == scopeOtherView);

        await manager.WriteStateAsync(scopeSelfView, Key1, Value1);
        await manager.WriteStateAsync(scopeOtherView, Key2, Value2);
        await manager.PublishUpdatesAsync(tracer: null);

        // Act: Update the key from one executor and delete it from another
        await manager.WriteStateAsync(scopeSelfView, Key1, "newValue");
        await manager.ClearStateAsync(scopeOtherView, Key1);
        Func<Task> act = async () => await manager.PublishUpdatesAsync(tracer: null);

        if (isSharedScope)
        {
            await act.Should().ThrowAsync<InvalidOperationException>("conflicting writes (update vs delete) should raise an exception when published");
        }
        else
        {
            await act.Should().NotThrowAsync("writes to private scopes should not be visible across executors");
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
        isSharedScope.Should().Be(scopeSelfView == scopeOtherView);

        await manager.WriteStateAsync(scopeSelfView, Key1, Value1);
        await manager.WriteStateAsync(scopeOtherView, Key2, Value2);
        await manager.PublishUpdatesAsync(tracer: null);

        // Act: Update the key from one, and clear the entire scope from another
        await manager.WriteStateAsync(scopeSelfView, Key1, "newValue");
        await manager.ClearStateAsync(scopeOtherView);
        Func<Task> act = async () => await manager.PublishUpdatesAsync(tracer: null);

        // Assert
        if (isSharedScope)
        {
            await act.Should().ThrowAsync<InvalidOperationException>("conflicting writes (update vs clear) should raise an exception when published");
        }
        else
        {
            await act.Should().NotThrowAsync("writes to private scopes should not be visible across executors");
        }
    }
}
