// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Http;

namespace Microsoft.Agents.AI.Hosting.Channels.UnitTests;

/// <summary>
/// Covers the per-request isolation surface: the <see cref="IsolationKeys"/> value type, the
/// <see cref="IsolationKeys.Current"/> AsyncLocal slot, the public header constants, the DI accessor, and the
/// header-lifting endpoint filter exercised directly. The filter is the ONLY seam Foundry-aware providers use
/// to find partition keys, so a regression here silently misroutes writes or leaks per-request state.
/// </summary>
public class IsolationKeysTests
{
    [Fact]
    public void Defaults_AreEmpty()
    {
        // Arrange / Act
        var keys = new IsolationKeys(null, null);

        // Assert
        Assert.Null(keys.UserKey);
        Assert.Null(keys.ChatKey);
        Assert.True(keys.IsEmpty);
    }

    [Fact]
    public void UserKeyOnly_IsNotEmpty()
    {
        // Arrange / Act
        var keys = new IsolationKeys("alice", null);

        // Assert
        Assert.Equal("alice", keys.UserKey);
        Assert.Null(keys.ChatKey);
        Assert.False(keys.IsEmpty);
    }

    [Fact]
    public void ChatKeyOnly_IsNotEmpty()
    {
        // Arrange / Act
        var keys = new IsolationKeys(null, "general");

        // Assert
        Assert.False(keys.IsEmpty);
    }

    [Fact]
    public void FullPair_IsNotEmpty()
    {
        // Arrange / Act
        var keys = new IsolationKeys("alice", "general");

        // Assert
        Assert.False(keys.IsEmpty);
    }

    [Fact]
    public void Current_DefaultsToNull()
    {
        // Arrange
        IsolationKeys.Current = null;

        // Assert
        Assert.Null(IsolationKeys.Current);
    }

    [Fact]
    public void Current_SetGetReset_RoundTrips()
    {
        // Arrange
        var previous = IsolationKeys.Current;

        // Act
        IsolationKeys.Current = new IsolationKeys("alice", "general");

        // Assert
        Assert.NotNull(IsolationKeys.Current);
        Assert.Equal("alice", IsolationKeys.Current!.UserKey);
        Assert.Equal("general", IsolationKeys.Current.ChatKey);

        // Reset
        IsolationKeys.Current = previous;
        Assert.Null(IsolationKeys.Current);
    }

    [Fact]
    public void Current_SetNull_Clears()
    {
        // Arrange
        IsolationKeys.Current = new IsolationKeys("alice", null);

        // Act
        IsolationKeys.Current = null;

        // Assert
        Assert.Null(IsolationKeys.Current);
    }

    [Fact]
    public void HeaderConstants_MatchFoundryContract()
    {
        // Assert
        Assert.Equal("x-agent-user-isolation-key", IsolationKeys.UserHeader);
        Assert.Equal("x-agent-chat-isolation-key", IsolationKeys.ChatHeader);
    }

    [Fact]
    public void Accessor_ReadsCurrent()
    {
        // Arrange
        var accessor = new IsolationKeysAccessor();
        IsolationKeys.Current = new IsolationKeys("bob", null);

        // Act
        var via = accessor.Current;

        // Assert
        Assert.NotNull(via);
        Assert.Equal("bob", via!.UserKey);

        // Cleanup
        IsolationKeys.Current = null;
        Assert.Null(accessor.Current);
    }

    [Fact]
    public async Task Filter_BothHeaders_BindsThenResetsAsync()
    {
        // Arrange
        IsolationKeys.Current = null;
        var filter = new IsolationKeysEndpointFilter();
        var http = new DefaultHttpContext();
        http.Request.Headers[IsolationKeys.UserHeader] = "alice-uid";
        http.Request.Headers[IsolationKeys.ChatHeader] = "general-cid";
        IsolationKeys? captured = null;

        // Act
        var result = await filter.InvokeAsync(
            new TestFilterContext(http),
            _ => { captured = IsolationKeys.Current; return ValueTask.FromResult<object?>("ok"); });

        // Assert - bound inside, reset after
        Assert.NotNull(captured);
        Assert.Equal("alice-uid", captured!.UserKey);
        Assert.Equal("general-cid", captured.ChatKey);
        Assert.Equal("ok", result);
        Assert.Null(IsolationKeys.Current);
    }

    [Fact]
    public async Task Filter_OnlyUserHeader_BindsChatNullAsync()
    {
        // Arrange
        var filter = new IsolationKeysEndpointFilter();
        var http = new DefaultHttpContext();
        http.Request.Headers[IsolationKeys.UserHeader] = "alice-uid";
        IsolationKeys? captured = null;

        // Act
        await filter.InvokeAsync(
            new TestFilterContext(http),
            _ => { captured = IsolationKeys.Current; return ValueTask.FromResult<object?>(null); });

        // Assert
        Assert.NotNull(captured);
        Assert.Equal("alice-uid", captured!.UserKey);
        Assert.Null(captured.ChatKey);
    }

    [Fact]
    public async Task Filter_OnlyChatHeader_BindsUserNullAsync()
    {
        // Arrange
        var filter = new IsolationKeysEndpointFilter();
        var http = new DefaultHttpContext();
        http.Request.Headers[IsolationKeys.ChatHeader] = "general-cid";
        IsolationKeys? captured = null;

        // Act
        await filter.InvokeAsync(
            new TestFilterContext(http),
            _ => { captured = IsolationKeys.Current; return ValueTask.FromResult<object?>(null); });

        // Assert
        Assert.NotNull(captured);
        Assert.Null(captured!.UserKey);
        Assert.Equal("general-cid", captured.ChatKey);
    }

    [Fact]
    public async Task Filter_NoHeaders_IsNoopAsync()
    {
        // Arrange
        IsolationKeys.Current = null;
        var filter = new IsolationKeysEndpointFilter();
        var http = new DefaultHttpContext();
        IsolationKeys? captured = new("sentinel", null);

        // Act
        await filter.InvokeAsync(
            new TestFilterContext(http),
            _ => { captured = IsolationKeys.Current; return ValueTask.FromResult<object?>(null); });

        // Assert - never bound
        Assert.Null(captured);
        Assert.Null(IsolationKeys.Current);
    }

    [Fact]
    public async Task Filter_EmptyHeaderValue_TreatedAsAbsentAsync()
    {
        // Arrange - empty user header must not bind an empty key; chat still binds
        var filter = new IsolationKeysEndpointFilter();
        var http = new DefaultHttpContext();
        http.Request.Headers[IsolationKeys.UserHeader] = "";
        http.Request.Headers[IsolationKeys.ChatHeader] = "general-cid";
        IsolationKeys? captured = null;

        // Act
        await filter.InvokeAsync(
            new TestFilterContext(http),
            _ => { captured = IsolationKeys.Current; return ValueTask.FromResult<object?>(null); });

        // Assert
        Assert.NotNull(captured);
        Assert.Null(captured!.UserKey);
        Assert.Equal("general-cid", captured.ChatKey);
    }

    [Fact]
    public async Task Filter_RestoresPreviousValueAsync()
    {
        // Arrange - a pre-existing Current must be restored, not clobbered to null
        var outer = new IsolationKeys("outer-user", null);
        IsolationKeys.Current = outer;
        var filter = new IsolationKeysEndpointFilter();
        var http = new DefaultHttpContext();
        http.Request.Headers[IsolationKeys.UserHeader] = "inner-user";

        // Act
        await filter.InvokeAsync(
            new TestFilterContext(http),
            _ => ValueTask.FromResult<object?>(null));

        // Assert - restored to outer
        Assert.Same(outer, IsolationKeys.Current);

        // Cleanup
        IsolationKeys.Current = null;
    }

    [Fact]
    public async Task Filter_PropagatesInnerResultAsync()
    {
        // Arrange
        var filter = new IsolationKeysEndpointFilter();
        var http = new DefaultHttpContext();
        http.Request.Headers[IsolationKeys.UserHeader] = "alice";

        // Act
        var result = await filter.InvokeAsync(
            new TestFilterContext(http),
            _ => ValueTask.FromResult<object?>(42));

        // Assert
        Assert.Equal(42, result);
    }

    private sealed class TestFilterContext(HttpContext httpContext) : EndpointFilterInvocationContext
    {
        public override HttpContext HttpContext { get; } = httpContext;

        public override IList<object?> Arguments { get; } = [];

        public override T GetArgument<T>(int index) => (T)this.Arguments[index]!;
    }
}
