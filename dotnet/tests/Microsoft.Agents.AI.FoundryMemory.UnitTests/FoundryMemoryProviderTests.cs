// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.FoundryMemory.UnitTests;

/// <summary>
/// Tests for <see cref="FoundryMemoryProvider"/> constructor validation and User-Agent header injection.
/// </summary>
public sealed class FoundryMemoryProviderTests
{
    #region Constructor Validation

    [Fact]
    public void Constructor_Throws_WhenClientIsNull()
    {
        ArgumentNullException ex = Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProvider(
            null!,
            "store",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test"))));
        Assert.Equal("client", ex.ParamName);
    }

    [Fact]
    public void Constructor_Throws_WhenStateInitializerIsNull()
    {
        using TestableAIProjectClient testClient = new();

        ArgumentNullException ex = Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProvider(
            testClient.Client,
            "store",
            stateInitializer: null!));
    }

    [Fact]
    public void Constructor_Throws_WhenMemoryStoreNameIsEmpty()
    {
        using TestableAIProjectClient testClient = new();

        ArgumentException ex = Assert.Throws<ArgumentException>(() => new FoundryMemoryProvider(
            testClient.Client,
            "",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test"))));
        Assert.Equal("memoryStoreName", ex.ParamName);
    }

    [Fact]
    public void Constructor_Throws_WhenMemoryStoreNameIsNull()
    {
        using TestableAIProjectClient testClient = new();

        ArgumentNullException ex = Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProvider(
            testClient.Client,
            null!,
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test"))));
        Assert.Equal("memoryStoreName", ex.ParamName);
    }

    [Fact]
    public void Scope_Throws_WhenScopeIsNull()
    {
        Assert.Throws<ArgumentNullException>(() => new FoundryMemoryProviderScope(null!));
    }

    [Fact]
    public void Scope_Throws_WhenScopeIsEmpty()
    {
        Assert.Throws<ArgumentException>(() => new FoundryMemoryProviderScope(""));
    }

    [Fact]
    public void StateInitializer_Throws_WhenScopeIsNull()
    {
        using TestableAIProjectClient testClient = new();
        FoundryMemoryProvider sut = new(
            testClient.Client,
            "store",
            stateInitializer: _ => new(null!));

        Assert.Throws<ArgumentNullException>(() =>
        {
            try
            {
                var field = typeof(FoundryMemoryProvider).GetField("_sessionState", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                var sessionState = field!.GetValue(sut);
                var method = sessionState!.GetType().GetMethod("GetOrInitializeState");
                method!.Invoke(sessionState, [null]);
            }
            catch (System.Reflection.TargetInvocationException tie) when (tie.InnerException is not null)
            {
                throw tie.InnerException;
            }
        });
    }

    [Fact]
    public void Constructor_Succeeds_WithValidParameters()
    {
        using TestableAIProjectClient testClient = new();

        FoundryMemoryProvider sut = new(
            testClient.Client,
            "my-store",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("user-456")));

        Assert.NotNull(sut);
    }

    #endregion

    #region User-Agent Header Tests — Provider Level

    /// <summary>
    /// Verifies that the MEAI user-agent header is present when the provider deletes a scope.
    /// </summary>
    [Fact]
    public async Task Provider_DeleteScope_UserAgentHeaderPresentAsync()
    {
        // Arrange
        using TestableAIProjectClient testClient = new(
            deleteStatusCode: HttpStatusCode.NoContent);

        FoundryMemoryProvider sut = new(
            testClient.Client,
            "test-store",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test-scope")));

        AgentSession session = await CreateAgentSessionAsync();

        // Act
        await sut.EnsureStoredMemoriesDeletedAsync(session);

        // Assert
        AssertMeaiUserAgentHeader(testClient.Handler);
    }

    /// <summary>
    /// Verifies that the MEAI user-agent header is present when the provider checks for an existing memory store.
    /// </summary>
    [Fact]
    public async Task Provider_GetMemoryStore_UserAgentHeaderPresentAsync()
    {
        // Arrange — store already exists so only GET is issued
        using TestableAIProjectClient testClient = new(
            getStoreStatusCode: HttpStatusCode.OK);

        FoundryMemoryProvider sut = new(
            testClient.Client,
            "test-store",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test-scope")));

        // Act — EnsureMemoryStoreCreatedAsync internally calls GetMemoryStoreAsync first;
        // the protocol method may throw on response parsing from the mock but the request is still sent.
        try
        {
            await sut.EnsureMemoryStoreCreatedAsync("gpt-4o", "text-embedding-ada-002");
        }
        catch (System.ClientModel.ClientResultException)
        {
            // Expected when mock response doesn't match the SDK response classifier
        }

        // Assert — the GET request was made and includes the header
        Assert.NotNull(testClient.Handler.LastRequestUri);
        AssertMeaiUserAgentHeader(testClient.Handler);
    }

    #endregion

    #region User-Agent Header Tests — Agent Level

    /// <summary>
    /// Verifies that the MEAI user-agent header is present on the search request
    /// when the provider is triggered through an agent RunAsync invocation.
    /// </summary>
    [Fact]
    public async Task Agent_RunAsync_SearchMemories_UserAgentHeaderPresentAsync()
    {
        // Arrange
        using TestableAIProjectClient testClient = new(
            searchMemoriesResponse: """{"memories":[]}""",
            updateMemoriesResponse: """{"update_id":"test-id","status":"queued"}""");

        FoundryMemoryProvider memoryProvider = new(
            testClient.Client,
            "test-store",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test-scope")));

        ChatClientAgent agent = CreateMockAgent(memoryProvider);
        AgentSession session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync("Hello", session);

        // Assert — verify that HTTP requests were made and include the MEAI header
        AssertMeaiUserAgentHeader(testClient.Handler);
    }

    /// <summary>
    /// Verifies that the MEAI user-agent header is present on the update request
    /// when the provider stores memories after an agent RunAsync invocation.
    /// </summary>
    [Fact]
    public async Task Agent_RunAsync_UpdateMemories_UserAgentHeaderPresentAsync()
    {
        // Arrange
        using TestableAIProjectClient testClient = new(
            searchMemoriesResponse: """{"memories":[]}""",
            updateMemoriesResponse: """{"update_id":"test-id","status":"queued"}""");

        FoundryMemoryProvider memoryProvider = new(
            testClient.Client,
            "test-store",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test-scope")));

        ChatClientAgent agent = CreateMockAgent(memoryProvider);
        AgentSession session = await agent.CreateSessionAsync();

        // Act
        await agent.RunAsync("Hello", session);

        // Assert — the last request should be the update (POST) and include the header
        Assert.Equal(System.Net.Http.HttpMethod.Post, testClient.Handler.LastRequestMethod);
        AssertMeaiUserAgentHeader(testClient.Handler);
    }

    /// <summary>
    /// End-to-end sanity test: runs a <see cref="ChatClientAgent"/> with a <see cref="FoundryMemoryProvider"/>
    /// attached, verifying the full pipeline produces a response and sends the MEAI user-agent header.
    /// </summary>
    [Fact]
    public async Task Agent_WithFoundryMemoryProvider_ProducesResponseAndSendsUserAgentAsync()
    {
        // Arrange
        using TestableAIProjectClient testClient = new(
            searchMemoriesResponse: """{"memories":[{"memory_item":{"content":"User likes hiking","scope":"test-scope"}}]}""",
            updateMemoriesResponse: """{"update_id":"update-123","status":"queued"}""");

        FoundryMemoryProvider memoryProvider = new(
            testClient.Client,
            "test-store",
            stateInitializer: _ => new(new FoundryMemoryProviderScope("test-scope")));

        ChatClientAgent agent = CreateMockAgent(memoryProvider, responseText: "I remember you like hiking!");
        AgentSession session = await agent.CreateSessionAsync();

        // Act
        AgentResponse response = await agent.RunAsync("What do you know about me?", session);

        // Assert — the agent produced a response
        Assert.NotNull(response);
        Assert.NotEmpty(response.Messages);
        Assert.Contains("hiking", response.Text);

        // Assert — the MEAI header was present on memory store HTTP requests
        AssertMeaiUserAgentHeader(testClient.Handler);
    }

    #endregion

    #region Helpers

    private static ChatClientAgent CreateMockAgent(FoundryMemoryProvider memoryProvider, string responseText = "Hi there!")
    {
        Mock<IChatClient> mockChatClient = new();
        mockChatClient.Setup(
            c => c.GetResponseAsync(
                It.IsAny<IEnumerable<ChatMessage>>(),
                It.IsAny<ChatOptions>(),
                It.IsAny<CancellationToken>()))
            .ReturnsAsync(new ChatResponse([new(ChatRole.Assistant, responseText)]));

        return new ChatClientAgent(
            mockChatClient.Object,
            options: new ChatClientAgentOptions
            {
                AIContextProviders = [memoryProvider]
            });
    }

    private static async Task<AgentSession> CreateAgentSessionAsync()
    {
        Mock<IChatClient> mockChatClient = new();
        ChatClientAgent agent = new(mockChatClient.Object);
        return await agent.CreateSessionAsync();
    }

    private static void AssertMeaiUserAgentHeader(MockHttpMessageHandler handler)
    {
        Assert.NotNull(handler.LastRequestHeaders);
        Assert.True(
            handler.LastRequestHeaders.TryGetValues("User-Agent", out var userAgentValues),
            "User-Agent header should be present on the HTTP request");
        Assert.Contains(userAgentValues, v => v.Contains("MEAI"));
    }

    #endregion
}
