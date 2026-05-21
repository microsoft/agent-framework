// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Moq;
using StackExchange.Redis;

namespace Microsoft.Agents.AI.Valkey.UnitTests;

/// <summary>
/// Unit tests for <see cref="ValkeyContextProvider"/>.
/// </summary>
public sealed class ValkeyContextProviderTests
{
    private static ValkeyContextProvider.State CreateValidState() =>
        new(new ValkeyProviderScope { UserId = "user-1" });

    private static Mock<IConnectionMultiplexer> CreateMockConnection(Mock<IDatabase>? dbMock = null)
    {
        var mockConnection = new Mock<IConnectionMultiplexer>();
        dbMock ??= new Mock<IDatabase>();
        mockConnection.Setup(c => c.GetDatabase(It.IsAny<int>(), It.IsAny<object>())).Returns(dbMock.Object);
        return mockConnection;
    }

    // --- Constructor tests ---

    [Fact]
    public void Constructor_WithConnection_SetsProperties()
    {
        var provider = new ValkeyContextProvider(
            CreateMockConnection().Object,
            _ => CreateValidState(),
            indexName: "test_idx",
            keyPrefix: "test:");

        Assert.NotNull(provider);
        Assert.Equal(10, provider.MaxResults);
    }

    [Fact]
    public void Constructor_NullConnection_Throws()
    {
        Assert.Throws<ArgumentNullException>(() =>
            new ValkeyContextProvider(
                (IConnectionMultiplexer)null!,
                _ => CreateValidState()));
    }

    [Fact]
    public void Constructor_NullStateInitializer_Throws()
    {
        Assert.Throws<ArgumentNullException>(() =>
            new ValkeyContextProvider(
                CreateMockConnection().Object,
                null!));
    }

    // --- State tests ---

    [Fact]
    public void State_ValidScope_SetsProperties()
    {
        var storageScope = new ValkeyProviderScope { UserId = "user-1", AgentId = "agent-1" };
        var searchScope = new ValkeyProviderScope { UserId = "user-1" };

        var state = new ValkeyContextProvider.State(storageScope, searchScope);

        Assert.Same(storageScope, state.StorageScope);
        Assert.Same(searchScope, state.SearchScope);
    }

    [Fact]
    public void State_NullSearchScope_DefaultsToStorageScope()
    {
        var storageScope = new ValkeyProviderScope { UserId = "user-1" };
        var state = new ValkeyContextProvider.State(storageScope);

        Assert.Same(storageScope, state.StorageScope);
        Assert.Same(storageScope, state.SearchScope);
    }

    [Fact]
    public void State_NullStorageScope_Throws()
    {
        Assert.Throws<ArgumentNullException>(() => new ValkeyContextProvider.State(null!));
    }

    // --- StateKeys tests ---

    [Fact]
    public void StateKeys_ReturnsProviderTypeName()
    {
        var provider = new ValkeyContextProvider(
            CreateMockConnection().Object,
            _ => CreateValidState());

        var keys = provider.StateKeys;
        Assert.Single(keys);
        Assert.Equal(nameof(ValkeyContextProvider), keys[0]);
    }

    [Fact]
    public void StateKeys_WithCustomKey_ReturnsCustomKey()
    {
        var provider = new ValkeyContextProvider(
            CreateMockConnection().Object,
            _ => CreateValidState(),
            stateKey: "my_key");

        var keys = provider.StateKeys;
        Assert.Single(keys);
        Assert.Equal("my_key", keys[0]);
    }

    // --- ValkeyProviderScope tests ---

    [Fact]
    public void ValkeyProviderScope_Properties_SetCorrectly()
    {
        var scope = new ValkeyProviderScope
        {
            ApplicationId = "app-1",
            AgentId = "agent-1",
            ThreadId = "thread-1",
            UserId = "user-1"
        };

        Assert.Equal("app-1", scope.ApplicationId);
        Assert.Equal("agent-1", scope.AgentId);
        Assert.Equal("thread-1", scope.ThreadId);
        Assert.Equal("user-1", scope.UserId);
    }

    [Fact]
    public void ValkeyProviderScope_CopyConstructor_ClonesAllProperties()
    {
        var original = new ValkeyProviderScope
        {
            ApplicationId = "app-1",
            AgentId = "agent-1",
            ThreadId = "thread-1",
            UserId = "user-1"
        };

        var copy = new ValkeyProviderScope(original);

        Assert.Equal(original.ApplicationId, copy.ApplicationId);
        Assert.Equal(original.AgentId, copy.AgentId);
        Assert.Equal(original.ThreadId, copy.ThreadId);
        Assert.Equal(original.UserId, copy.UserId);
    }

    [Fact]
    public void ValkeyProviderScope_CopyConstructor_NullSource_Throws()
    {
        Assert.Throws<ArgumentNullException>(() => new ValkeyProviderScope(null!));
    }

    // --- MaxResults tests ---

    [Fact]
    public void MaxResults_DefaultsTo10()
    {
        var provider = new ValkeyContextProvider(
            CreateMockConnection().Object,
            _ => CreateValidState());

        Assert.Equal(10, provider.MaxResults);
    }

    [Fact]
    public void MaxResults_CanBeSet()
    {
        var provider = new ValkeyContextProvider(
            CreateMockConnection().Object,
            _ => CreateValidState())
        {
            MaxResults = 25
        };

        Assert.Equal(25, provider.MaxResults);
    }

    // --- EscapeTag tests ---

    [Theory]
    [InlineData("simple", "simple")]
    [InlineData("has space", "has\\ space")]
    [InlineData("has{brace}", "has\\{brace\\}")]
    [InlineData("has@at", "has\\@at")]
    [InlineData("has|pipe", "has\\|pipe")]
    [InlineData("back\\slash", "back\\\\slash")]
    [InlineData("my-agent-1", "my\\-agent\\-1")]
    [InlineData("v2.0.1", "v2\\.0\\.1")]
    [InlineData("ns:key", "ns\\:key")]
    [InlineData("it's", "it\\'s")]
    [InlineData("say\"hi\"", "say\\\"hi\\\"")]
    public void EscapeTag_EscapesSpecialCharacters(string input, string expected)
    {
        Assert.Equal(expected, ValkeyContextProvider.EscapeTag(input));
    }

    // --- EscapeQuery tests ---

    [Theory]
    [InlineData("simple text", "simple text")]
    [InlineData("hello@world", "hello\\@world")]
    [InlineData("a*b", "a\\*b")]
    [InlineData("(test)", "\\(test\\)")]
    [InlineData("no:colons", "no\\:colons")]
    public void EscapeQuery_EscapesSpecialCharacters(string input, string expected)
    {
        Assert.Equal(expected, ValkeyContextProvider.EscapeQuery(input));
    }

    // --- ParseSearchResults tests ---

    [Fact]
    public void ParseSearchResults_NullResult_ReturnsEmpty()
    {
        var result = RedisResult.Create(RedisValue.Null);
        var docs = ValkeyContextProvider.ParseSearchResults(result);
        Assert.Empty(docs);
    }

    [Fact]
    public void ParseSearchResults_ValidResult_ParsesDocuments()
    {
        // FT.SEARCH returns: [total_count, doc_id, [field, value, ...], ...]
        var inner = new RedisResult[]
        {
            RedisResult.Create((RedisValue)"content"),
            RedisResult.Create((RedisValue)"hello world"),
            RedisResult.Create((RedisValue)"role"),
            RedisResult.Create((RedisValue)"user"),
        };

        var results = new RedisResult[]
        {
            RedisResult.Create((RedisValue)1),           // total count
            RedisResult.Create((RedisValue)"doc:1"),      // doc id
            RedisResult.Create(inner),                     // fields
        };

        var result = RedisResult.Create(results);
        var docs = ValkeyContextProvider.ParseSearchResults(result);

        Assert.Single(docs);
        Assert.Equal("hello world", docs[0]["content"]);
        Assert.Equal("user", docs[0]["role"]);
    }

    // --- Dispose tests ---

    [Fact]
    public async Task DisposeAsync_CalledTwice_NoOpAsync()
    {
        var provider = new ValkeyContextProvider(
            CreateMockConnection().Object,
            _ => CreateValidState());

        await provider.DisposeAsync();
        await provider.DisposeAsync();
    }

    [Fact]
    public async Task AfterDispose_ThrowsObjectDisposedExceptionAsync()
    {
        var provider = new ValkeyContextProvider(
            CreateMockConnection().Object,
            _ => CreateValidState());

        await provider.DisposeAsync();

        await Assert.ThrowsAsync<ObjectDisposedException>(() =>
            provider.InvokedAsync(
                TestHelpers.CreateContextProviderInvokedContext(
                    [new Extensions.AI.ChatMessage(Extensions.AI.ChatRole.User, "test")],
                    [new Extensions.AI.ChatMessage(Extensions.AI.ChatRole.Assistant, "reply")])).AsTask());
    }
}
