// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

public sealed class InMemoryAgentSessionStoreTests
{
    [Theory]
    [InlineData("cedar:u-elm", "fir", "trail", "cedar", "elm:u-fir", "trail")]
    [InlineData("cedar", "elm:c-fir", "trail", "cedar", "elm", "fir:c-trail")]
    [InlineData("cedar:c-elm", null, "trail", "cedar", null, "elm:c-trail")]
    [InlineData("cedar:u-elm", null, "trail", "cedar", "elm", "trail")]
    [InlineData("cedar", "elm", "trail", "maple", "elm", "trail")]
    [InlineData(null, "elm", "trail", "cedar", "elm", "trail")]
    [InlineData(" ", "elm", "trail", null, "elm", "trail")]
    [InlineData(" cedar", "elm", "trail", "cedar", "elm", "trail")]
    [InlineData("cedar ", "elm", "trail", "cedar", "elm", "trail")]
    [InlineData("Cedar", "elm", "trail", "cedar", "elm", "trail")]
    [InlineData("cedar", "elm", "trail", "cedar", "fir", "trail")]
    [InlineData("cedar", "elm", "trail", "cedar", null, "trail")]
    [InlineData("cedar", " elm", "trail", "cedar", "elm", "trail")]
    [InlineData("cedar", "elm ", "trail", "cedar", "elm", "trail")]
    [InlineData("cedar", "Elm", "trail", "cedar", "elm", "trail")]
    [InlineData("cedar", "elm", "trail", "cedar", "elm", "glade")]
    [InlineData("cedar", "elm", " trail", "cedar", "elm", "trail")]
    [InlineData("cedar", "elm", "trail ", "cedar", "elm", "trail")]
    [InlineData("cedar", "elm", "Trail", "cedar", "elm", "trail")]
    [InlineData("cedar", "elm", "", "cedar", "elm", " ")]
    public async Task SaveSessionAsync_CompositeIdentifiersPreserveBoundariesAsync(
        string? firstAgentName, string? firstUserId, string firstConversationId,
        string? secondAgentName, string? secondUserId, string secondConversationId)
    {
        // Arrange
        var store = new InMemoryAgentSessionStore();
        var firstAgent = new TestAgent(firstAgentName);
        var secondAgent = new TestAgent(secondAgentName);

        // Act & Assert
        await store.SaveSessionAsync(firstAgent, firstConversationId, new TestSession("first"), firstUserId);
        Assert.Null(await store.GetSessionAsync(secondAgent, secondConversationId, secondUserId));

        await store.SaveSessionAsync(secondAgent, secondConversationId, new TestSession("second"), secondUserId);
        var first = await store.GetSessionAsync(firstAgent, firstConversationId, firstUserId);
        var second = await store.GetSessionAsync(secondAgent, secondConversationId, secondUserId);

        Assert.Equal("first", Assert.IsType<TestSession>(first).Value);
        Assert.Equal("second", Assert.IsType<TestSession>(second).Value);
    }

    [Theory]
    [InlineData(null, null, null, null)]
    [InlineData(null, null, "", "")]
    [InlineData("", "", null, " \t\r\n")]
    [InlineData(null, "elm", "", "elm")]
    [InlineData("cedar", null, "cedar", "")]
    [InlineData("cedar", null, "cedar", "   ")]
    [InlineData("cedar", null, "cedar", "\t\r\n")]
    [InlineData("cedar", "elm", "cedar", "elm")]
    [InlineData(" cedar ", " elm ", " cedar ", " elm ")]
    public async Task SaveSessionAsync_EquivalentIdentifiersReuseAndReplaceSessionAsync(
        string? firstAgentName, string? firstUserId, string? secondAgentName, string? secondUserId)
    {
        // Arrange
        var store = new InMemoryAgentSessionStore();
        var firstAgent = new TestAgent(firstAgentName);
        var secondAgent = new TestAgent(secondAgentName);
        Assert.NotEqual(firstAgent.Id, secondAgent.Id);

        // Act & Assert
        await store.SaveSessionAsync(firstAgent, "trail", new TestSession("initial"), firstUserId);
        var restored = await store.GetSessionAsync(secondAgent, "trail", secondUserId);
        Assert.Equal("initial", Assert.IsType<TestSession>(restored).Value);

        await store.SaveSessionAsync(secondAgent, "trail", new TestSession("updated"), secondUserId);
        var updated = await store.GetSessionAsync(firstAgent, "trail", firstUserId);
        Assert.Equal("updated", Assert.IsType<TestSession>(updated).Value);
    }

    private sealed class TestSession(string value) : AgentSession
    {
        public string Value { get; } = value;
    }

    private sealed class TestAgent(string? name) : AIAgent
    {
        public override string? Name => name;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(
            CancellationToken cancellationToken = default) =>
            ValueTask.FromResult<AgentSession>(new TestSession(string.Empty));

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(
            AgentSession session,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default)
        {
            var testSession = Assert.IsType<TestSession>(session);
            return ValueTask.FromResult(JsonSerializer.SerializeToElement(testSession.Value));
        }

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(
            JsonElement serializedState,
            JsonSerializerOptions? jsonSerializerOptions = null,
            CancellationToken cancellationToken = default) =>
            ValueTask.FromResult<AgentSession>(new TestSession(serializedState.GetString()!));

        protected override Task<AgentResponse> RunCoreAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
            IEnumerable<ChatMessage> messages,
            AgentSession? session = null,
            AgentRunOptions? options = null,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();
    }
}
