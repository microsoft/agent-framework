// Copyright (c) Microsoft. All rights reserved.

using FluentAssertions;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.UnitTests;

public class StateKeyObjectTests
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
    public void Test_UpdateKey_IsMatchingScope()
    {
        const string Key1 = "key1";

        UpdateKey privateScope1Key = new("executor1", null, Key1);
        UpdateKey privateScope2Key = new("executor2", null, Key1);

        ScopeId privateScope1 = new("executor1", null);
        ScopeId privateScope2 = new("executor2", null);

        ValidateMatch(privateScope1Key, privateScope1, expectedStrict: true, expectedLoose: true);
        ValidateMatch(privateScope1Key, privateScope2, expectedStrict: false, expectedLoose: false);
        ValidateMatch(privateScope2Key, privateScope1, expectedStrict: false, expectedLoose: false);
        ValidateMatch(privateScope2Key, privateScope2, expectedStrict: true, expectedLoose: true);

        UpdateKey sharedScope1Key = new("executor1", "sharedScope", Key1);
        UpdateKey sharedScope2Key = new("executor2", "sharedScope", Key1);

        ScopeId sharedScope1 = new("executor1", "sharedScope");
        ScopeId sharedScope2 = new("executor2", "sharedScope");

        ValidateMatch(sharedScope1Key, sharedScope1, expectedStrict: true, expectedLoose: true);
        ValidateMatch(sharedScope1Key, sharedScope2, expectedStrict: false, expectedLoose: true);
        ValidateMatch(sharedScope2Key, sharedScope1, expectedStrict: false, expectedLoose: true);
        ValidateMatch(sharedScope2Key, sharedScope2, expectedStrict: true, expectedLoose: true);

        // Cross checks between private and shared scopes should never match
        ValidateMatch(privateScope1Key, sharedScope1, expectedStrict: false, expectedLoose: false);
        ValidateMatch(privateScope1Key, sharedScope2, expectedStrict: false, expectedLoose: false);
        ValidateMatch(privateScope2Key, sharedScope1, expectedStrict: false, expectedLoose: false);
        ValidateMatch(privateScope2Key, sharedScope2, expectedStrict: false, expectedLoose: false);

        ValidateMatch(sharedScope1Key, privateScope1, expectedStrict: false, expectedLoose: false);
        ValidateMatch(sharedScope1Key, privateScope2, expectedStrict: false, expectedLoose: false);
        ValidateMatch(sharedScope2Key, privateScope1, expectedStrict: false, expectedLoose: false);
        ValidateMatch(sharedScope2Key, privateScope2, expectedStrict: false, expectedLoose: false);

        static void ValidateMatch(UpdateKey key, ScopeId scope, bool expectedStrict, bool expectedLoose)
        {
            key.IsMatchingScope(scope, strict: true).Should().Be(expectedStrict);
            key.IsMatchingScope(scope, strict: false).Should().Be(expectedLoose);
        }
    }
}
